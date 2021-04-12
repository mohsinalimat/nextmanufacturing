# -*- coding: utf-8 -*-
# Copyright (c) 2021, Dexciss Technology and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from datetime import datetime
import json
from frappe import _

class MaterialConsumption(Document):
    def set_consume_material(self):
        if self.material_consumption_detail:
            line_id = None
            lst = []
            total_qty = 0
            for res in self.material_consumption_detail:
                if res.qty_to_consume:
                    line_id = res.consume_item
                    lst.append({
                        "item_code": res.item,
                        "stock_uom": res.uom,
                        "warehouse": res.warehouse,
                        "batch_no": res.batch,
                        "balance_qty": res.balance_qty,
                        "expiry_date_batch": res.expiry_date_batch,
                        "life_left_batch": res.life_left_batch,
                        "qty_to_consume": res.qty_to_consume,
                        "consume_item": res.consume_item
                        })
                    total_qty += res.qty_to_consume
            if line_id:
                l_doc = frappe.get_doc("Materials to Consume Items",line_id)
                l_doc.data = json.dumps(lst)
                l_doc.qty_issued = total_qty
                l_doc.status = "Assigned"
                l_doc.save(ignore_permissions=True)
        return True

    def on_submit(self):
        self.make_stock_entry()
        # if self.job_card:
        #     job = frappe.get_doc("Job Card",self.job_card)
        #     for res in self.materials_to_consume:
        #         total = 0
        #         if res.data:
        #             for line in json.loads(res.data):
        #                 total += line.get('qty_to_consume')
        #         job_line = frappe.get_list("Job Card Item", filters={'parent': job.name, "item_code": res.item_code}, fields=["name"])
        #         for l in job_line:
        #             line = frappe.get_doc("Job Card Item", l.name)
        #             if line.transferred_qty:
        #                 line.transferred_qty += total
        #             else:
        #                 line.transferred_qty = total
        #             line.db_update()
        #         job.transferred_qty = total
        #         job.db_update()




    def make_stock_entry(self):
        if self.type == "Manual":
            lst = []
            for res in self.materials_to_consume:
                if res.status == 'Not Assigned':
                    lst.append(0)
                else:
                    lst.append(1)
            if 1 not in lst:
                frappe.throw(_("At least one product required to be consumed"))
            else:
                stock_entry = frappe.new_doc("Stock Entry")
                stock_entry.work_order = self.work_order
                stock_entry.job_card = self.job_card
                stock_entry.material_consumption = self.name
                stock_entry.company = self.company
                stock_entry.stock_entry_type = "Material Consumption for Manufacture"
                total_transfer_qty = 0
                for res in self.materials_to_consume:
                    if res.data:
                        for line in json.loads(res.data):
                            expense_account, cost_center = frappe.db.get_values("Company", self.company, ["default_expense_account", "cost_center"])[0]
                            
                            get_wo_doc = frappe.get_doc("Work Order",self.work_order)
                            
                            
                            item_expense_account, item_cost_center = frappe.db.get_value("Item Default",
                                                                            {'parent': line.get('item_code'), 'company': self.company},
                                                                                         ["expense_account", "buying_cost_center"])
                            if not cost_center and not item_cost_center:
                                frappe.throw(_("Please update default Cost Center for company {0}").format(self.company))

                            itm_doc = frappe.get_doc("Item",line.get('item_code'))
                            se_item = stock_entry.append("items")
                            se_item.item_code = line.get('item_code')
                            se_item.qty = line.get('qty_to_consume')
                            se_item.s_warehouse = line.get('warehouse')
                            se_item.t_warehouse = self.t_warehouse
                            se_item.item_name = itm_doc.item_name
                            se_item.description = itm_doc.description
                            se_item.uom = line.get('stock_uom')
                            se_item.stock_uom = line.get('stock_uom')
                            se_item.batch_no = line.get('batch_no')
                            se_item.expense_account = item_expense_account or expense_account
                            #se_item.cost_center = item_cost_center or cost_center
                            se_item.cost_center = get_wo_doc.rm_cost_center
            
                            # in stock uom
                            se_item.conversion_factor = 1.00
                            # if self.type == "Manual" and line.get('type') == "RM":
                            #     qty = line.get('issued_qty') * line.get('weight_per_unit')
                            #     total_transfer_qty += qty
                            #if self.type == "Pick List":
                            item_master_wigth_per_unit = frappe.db.get_value("Item", {"item_code":line.get('item_code')}, 'weight_per_unit')
                            if item_master_wigth_per_unit:
                                qty = line.get('picked_qty') * item_master_wigth_per_unit
                                total_transfer_qty += qty
                            if not item_master_wigth_per_unit:
                                m = "Please Enter weight per unit for item {0}".format(line.get('item_code'))
                                frappe.throw(_(m))
                # calculate material as per yeild
                bom_yeild = frappe.db.get_value("Work Order", {"name":self.work_order},['bom_yeild'])
                
                if(bom_yeild > 0):
                    calculated_qty = (total_transfer_qty) * (bom_yeild/100)
                else:
                    calculated_qty = total_transfer_qty
                stock_entry.from_bom = 1
                stock_entry.fg_completed_qty = calculated_qty
                stock_entry.set_actual_qty()
                stock_entry.calculate_rate_and_amount()
                stock_entry.insert(ignore_permissions=True)
                stock_entry.validate()
                # did not understand thats why removing
                #stock_entry.flags.ignore_validate_update_after_submit = True
                stock_entry.flags.ignore_validate = True
                stock_entry.submit()
        else:
            stock_entry = frappe.new_doc("Stock Entry")
            stock_entry.work_order = self.work_order
            stock_entry.job_card = self.job_card
            stock_entry.material_consumption = self.name
            stock_entry.company = self.company
            stock_entry.stock_entry_type = "Material Consumption for Manufacture"
            total_transfer_qty = 0
            for res in self.pick_list_item:
                expense_account, cost_center = \
                frappe.db.get_values("Company", self.company, ["default_expense_account", "cost_center"])[0]
                item_expense_account, item_cost_center = frappe.db.get_value("Item Default",
                                                                             {'parent': res.item_code,
                                                                              'company': self.company},
                                                                             ["expense_account",
                                                                              "buying_cost_center"])
                get_wo_doc = frappe.get_doc("Work Order",self.work_order)

                if not cost_center and not item_cost_center:
                    frappe.throw(_("Please update default Cost Center for company {0}").format(self.company))

                itm_doc = frappe.get_doc("Item", res.item_code)
                se_item = stock_entry.append("items")
                se_item.item_code = res.item_code
                se_item.qty = res.picked_qty
                se_item.s_warehouse = res.warehouse
                se_item.s_warehouse = self.s_warehouse
                se_item.item_name = itm_doc.item_name
                se_item.description = itm_doc.description
                se_item.uom = res.uom
                se_item.stock_uom = res.stock_uom
                se_item.batch_no = res.batch_no
                se_item.expense_account = item_expense_account or expense_account
                #se_item.cost_center = item_cost_center or cost_center
                se_item.cost_center = get_wo_doc.rm_cost_center
                # in stock uom
                se_item.conversion_factor = res.conversion_factor
            
                # if self.type == "Pick List":
                item_master_wigth_per_unit = frappe.db.get_value("Item", {"item_code":res.get('item_code')}, 'weight_per_unit')
                if item_master_wigth_per_unit:
                    qty = res.get('picked_qty') * item_master_wigth_per_unit
                    total_transfer_qty += qty
                if not item_master_wigth_per_unit:
                    m = "Please Enter weight per unit for item {0}".format(line.get('item_code'))
                    frappe.throw(_(m))
            bom_yeild = frappe.db.get_value("Work Order", {"name":self.work_order},['bom_yeild'])
            if bom_yeild:
                if(bom_yeild > 0):
                    calculated_qty = (total_transfer_qty) * (bom_yeild/100)
            else:
                calculated_qty = total_transfer_qty
            stock_entry.from_bom = 1
            stock_entry.fg_completed_qty = calculated_qty
            stock_entry.set_actual_qty()
            stock_entry.calculate_rate_and_amount()
            stock_entry.insert(ignore_permissions=True)
            stock_entry.validate()
            #stock_entry.flags.ignore_validate_update_after_submit = True
            stock_entry.flags.ignore_validate = True
            stock_entry.submit()

@frappe.whitelist()
def get_available_qty_data(line_id, company, item_code, warehouse, has_batch_no=None, data=None):
    if not data:
		#print("#")
        if has_batch_no == '1':
            # warehouse_lst = [warehouse]
            # wr_house = frappe.db.sql("""select name from `tabWarehouse` 
            #                 where company = %s and parent_warehouse = %s""", (company, warehouse), as_dict=True)
            # for w in wr_house:
            #     warehouse_lst.append(w.get('name'))
            # query = """select sle.item_code, warehouse, sle.company, sle.stock_uom, batch_no, sum(sle.actual_qty) as balance_qty 
            #         from `tabStock Ledger Entry` sle force index (posting_sort_index) 
            #         where sle.docstatus < 2 and is_cancelled = 0 and sle.batch_no is not null 
            #         and company = '{0}' and sle.item_code = '{1}'""".format(company, item_code)
            # if len(warehouse_lst) > 1:
            #     query += " and warehouse in {0}".format(tuple(warehouse_lst))
            # else:
            #     query += " and warehouse = '{0}'".format(warehouse_lst[0])

            query += " group by sle.item_code, warehouse,sle.company, batch_no, sle.stock_uom order by warehouse, batch_no"
            result = frappe.db.sql(query, as_dict=True)
            for res in result:
                if res.get('batch_no'):
                    batch = frappe.get_doc("Batch",res.get('batch_no'))
                    if batch.expiry_date:
                        res['expiry_date'] = batch.expiry_date
                        if batch.expiry_date >= datetime.now().date():
                            res['life_left_batch'] = (batch.expiry_date - datetime.now().date()).days
            return result
        else:
            warehouse_lst = [warehouse]
            wr_house = frappe.db.sql("""select name from `tabWarehouse` 
                    where company = %s and parent_warehouse = %s""",(company,warehouse),as_dict=True)
            for w in wr_house:
                warehouse_lst.append(w.get('name'))
            query = """select sle.item_code, warehouse, sle.company, sle.stock_uom, sum(sle.actual_qty) as balance_qty 
            from `tabStock Ledger Entry` sle force index (posting_sort_index) 
            where sle.docstatus < 2 and is_cancelled = 0 and company = '{0}' and sle.item_code = '{1}'""".format(company,item_code)
            if len(warehouse_lst) > 1:
                query += " and warehouse in {0}".format(tuple(warehouse_lst))
            else:
                query += " and warehouse = '{0}'".format(warehouse_lst[0])

            query +=" group by sle.item_code, warehouse,sle.company, sle.stock_uom order by warehouse"
            result = frappe.db.sql(query,as_dict=True)
            return result
    else:
        return json.loads(data)


@frappe.whitelist()
def add_pick_list_item(doc_name,pick_list):
    frappe.db.sql("delete from `tabPick List Item` where parent = %s", (doc_name))
    pick_list = frappe.get_doc("Pick List",pick_list)
    try:
        doc = frappe.get_doc("Material Consumption", doc_name)
    except:
        frappe.throw(_("Please save this document before adding any item"))
    #if is_existing_doc:
    
    for res in pick_list.locations:
        doc.append('pick_list_item',{
            'item_code': res.item_code,
            'item_name': res.item_name,
            'description': res.description,
            'item_group': res.item_group,
            'warehouse': res.warehouse,
            'qty': res.qty,
            'stock_qty': res.stock_qty,
            'picked_qty': res.picked_qty,
            'uom': res.uom,
            'stock_uom': res.stock_uom,
            'serial_no': res.serial_no,
            'batch_no': res.batch_no,
            'sales_order': res.sales_order,
            'sales_order_item': res.sales_order_item,
            'material_request': res.material_request,
            'material_request_item': res.material_request_item
        })
        doc.type = 'Pick List'
        doc.save(ignore_permissions=True)
    # else:
    #     data = {}
    #     name = pick_list.get('work_order')
    #     if not name:
    #         frappe.throw("Work Order not found for selected pick list")
    #     wo_doc = frappe.get_doc('Work Order',name)
    #     data['wo'] = name
    #     data['t_warehouse'] = wo_doc.wip_warehouse
    #     data['item_list']  = pick_list.locations
    #     return data


@frappe.whitelist()
def consumption_list(wo):
    query = """SELECT * FROM `tabWork Order Item` where parent = '{0}';""".format(wo)

    all_items = frappe.db.sql(query, as_dict = True)
    data_list = []
    for item in all_items:
        print("*****************")
        print(item)
        qty = item.get('transferred_qty') - item.get('consumed_qty')
        data = {
            "item_code":item.get("item_code"),
            "transferred_qty": item.get('transferred_qty'),
            "consumed_qty": item.get('consumed_qty'),
            "qty": qty,
            "stock_qty": 10
        }
        #if qty > 0:
        data_list.append(data)
    if(len(data_list) == 0):
        frappe.msgprint("No item Found")
    return data_list
    # print("***********************************")
    # print(source_name)
    # all_items_list = frappe.bd.get_all("")
    # for_qty = for_qty or json.loads(target_doc).get('for_qty')
    # max_finished_goods_qty = frappe.db.get_value('Work Order', source_name, 'qty')
    # def update_item_quantity(source, target, source_parent):
    #     print("*************************", source)
    #     pending_to_issue = flt(source.required_qty) - flt(source.transferred_qty)
    #     desire_to_transfer = flt(source.required_qty) / max_finished_goods_qty * flt(for_qty)

    #     qty = 0
    #     # if desire_to_transfer <= pending_to_issue:
    #     #     qty = desire_to_transfer
    #     elif pending_to_issue > 0:
    #         qty = pending_to_issue

    #     #if qty:
    #     target.qty = 10
    #     target.stock_qty = 10
    #     target.uom = frappe.get_value('Item', source.item_code, 'stock_uom')
    #     target.stock_uom = target.uom
    #     target.conversion_factor = 1
    #     # else:
    #     #     target.delete()

    # doc = get_mapped_doc('Work Order', source_name, {
    #     'Work Order': {
    #         'doctype': 'Pick List',
    #         'validation': {
    #             'docstatus': ['in', [1]]
    #         }
    #     }
    #     # 'Work Order Item': {
    #     #     'doctype': 'Pick List Item',
    #     #     'postprocess': update_item_quantity,
    #     #     'condition': lambda doc: abs(doc.transferred_qty) < abs(doc.required_qty)
    #     # },
    # }, target_doc)

    # wo_doc = frappe.get_doc('Work Order', wo)
    # for item in wo_doc.get("required_items"):
    #     actual_qty_to_pass = item.get("required_qty") - item.get("transferred_qty")
    #     item_details = frappe.db.get_value("Item", {"item_code":item.get("item_code")}, ['item_group','description'], as_dict = True)
    #     #stock_qty = frappe.db.get_value("Bin", {"item_code":item.get("item_code"), "warehouse":item.get("source_warehouse") }, ['item_group','description'])
    #     if actual_qty_to_pass > 0:
    #         doc.append("locations", {
    #         "item_code": item.get("item_code"),
    #         "item_name": item.get("item_name"),
    #         "warehouse": item.get("source_warehouse"),
    #         "qty": 10,
    #         "stock_qty": actual_qty_to_pass,      # need to remove gardcoded stock qty
    #         "description": item_details.get('description'),
    #         'item_group': item_details.get('item_group')

    #     })

    # doc.for_qty = 10
    # doc.set_item_locations()
    # print("**************run "*200)
    # return doc

@frappe.whitelist()
def set_item_locations(self, save=False):
    print("****@"*200)
    print(self)
