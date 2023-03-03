# -*- coding: utf-8 -*-
import dateutil.utils

from odoo import models, fields, api, _
from datetime import datetime
from .. import extensions
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'
    total_in_text = fields.Char(compute='set_amount_text', string='Total en letra')
    # state = fields.Selection([('draft', 'Quotation'), ('sent', 'Quotation Sent'), ('sale_conf', 'Validación ventas'), ('purchase_conf', 'Validación compras'), ('credito_conf', 'Validación credito'), ('sale', 'Sales Order'), ('done', 'Locked'), ('cancel', 'Cancelled'), ], string='Status', readonly=True, copy=False, index=True, tracking=3, default='draft')
    state = fields.Selection([('draft', 'Quotation'), ('sent', 'Quotation Sent'), ('sale_conf', 'Validación ventas'), ('credito_conf', 'Validación credito'), ('sale', 'Sales Order'), ('done', 'Locked'), ('cancel', 'Cancelled'), ], string='Status', readonly=True, copy=False, index=True, tracking=3, default='draft')
    purchase_ids = fields.Many2many('purchase.order', string='OC', readonly=True)
    check_solicitudes = fields.Boolean(default=False, compute='solicitud_reduccion')
    albaran = fields.Many2one('stock.picking', 'Albaran')
    states_proposals = fields.Many2many('proposal.state', string='Estados de propuestas', compute='set_states_proposal')
    requirements_line_ids = fields.One2many('requiriment.client', 'x_order_id', 'Requerimientos')
    proposal_line_ids = fields.Many2many('proposal.purchases', compute='get_proposals')
    partner_loc_ids = fields.Many2many('res.partner', compute='get_partner')
    partner_child = fields.Many2one('res.partner', 'Solicitante')
    partner_id = fields.Many2one('res.partner', string='Customer', readonly=True,
        states={'draft': [('readonly', False)], 'sent': [('readonly', False)]},
        required=True, change_default=True, index=True, tracking=1,
        domain="[('type', '!=', 'private'), ('company_id', 'in', (False, company_id))]",)
    partner_id_uso_cfdi = fields.Selection('Uso CFDI', related='partner_id.x_studio_uso_de_cfdi')
    partner_id_payment_method = fields.Char('Forma de pago',related='partner_id.x_studio_mtodo_de_pago.name')


    def _prepare_invoice(self):
        vals = super(SaleOrder,self)._prepare_invoice()
        vals.update({'l10n_mx_edi_usage':self.partner_id.x_studio_uso_de_cfdi})
        vals.update({'l10n_mx_edi_payment_method_id':self.partner_id.x_studio_mtodo_de_pago})
        return vals

    @api.depends('requirements_line_ids')
    def get_proposals(self):
        for record in self:
            record.proposal_line_ids = [(6, 0, record.requirements_line_ids.mapped('x_lines_proposal.id'))]

    @api.depends('proposal_line_ids')
    def set_states_proposal(self):
        for record in self:
            record.states_proposals = [(5,0,0)]
            for li in record.proposal_line_ids:
                record.states_proposals = [(0, 0, {'name': li.x_name+":"+str(dict(li._fields['x_state'].selection).get(li.x_state)) })]

    @api.onchange('partner_child')
    def set_partner_id(self):
        for record in self:
            if record.partner_child:
                if record.partner_child.parent_id:
                    record.partner_id = record.partner_child.parent_id
                else:
                    record.partner_id = record.partner_child
                record.x_studio_cliente_de_marketplace = record.partner_child.name
                record.user_id = self.env.user.id

    @api.onchange('partner_id')
    def onchange_partner_id(self):
        r = super(SaleOrder, self).onchange_partner_id()
        self.update({'user_id': self.env.user.id})
        return r

    def update_stock(self):
        for rec in self.order_line:
            rec.get_stock()

    @api.model
    def create(self, vals):
        if 'user_id' in vals:
            vals['user_id'] = self.env.user.id
        return super(SaleOrder, self).create(vals)

    @api.depends('amount_total')
    def set_amount_text(self):
        for record in self:
            if record.amount_total:
                record.total_in_text = extensions.text_converter.number_to_text_es(record.amount_total)
            else:
                record.total_in_text = extensions.text_converter.number_to_text_es(0)

    def conf_credito(self):
        self.write({'x_aprovacion_compras': True, 'x_bloqueo': False})
        self.action_confirm()

    def conf_purchase(self):
        total = self.partner_id.credit_rest - self.amount_total
        check = total >= 0 if self.payment_term_id.id != 1 else False
        cliente = self.partner_id.x_studio_triple_a
        if cliente and check:
            self.write({'x_bloqueo': False, 'x_aprovacion_compras': True})
            self.action_confirm()
        else:
            self.write({'state': 'credito_conf'})

    def conf_ventas(self):
        order_lines = self.order_line
        for ol in order_lines:
            ol.check_price_reduce = False
            ol.price_reduce_solicit = False
        registro = self.order_line.filtered(lambda x: x.product_id.virtual_available <= 0).mapped('id')
        if registro != []:
            self.write({'x_aprovar': True, 'state': 'credito_conf'})
        if registro == []:
            total = self.partner_id.credit_rest - self.amount_total
            check = total >= 0 if self.payment_term_id.id != 1 else False
            cliente = self.partner_id.x_studio_triple_a
            #facturas = self.partner_id.invoice_ids.filtered(lambda x: x.invoice_date_due != False).filtered(lambda x: x.invoice_date_due < fields.date.today() and x.state == 'posted' and x.payment_state in ('not_paid', 'partial')).mapped('id')
            if check and cliente:
                self.write({'x_bloqueo': False, 'x_aprovacion_compras': True})
                return self.action_confirm()
            else:
                self.write({'state': 'credito_conf'})


    def is_valid_order_sale(self):
        valid = True
        message = ''
        dic_nuevos_precios = {}
        dic_cantidades_disponibles ={}
        if len(self.order_line) <= 0:
            valid = False
            message = 'No hay productos en la cotización'
            return valid, message


        for i,line in enumerate(self.order_line,start=1):
            margen = line.product_id.x_fabricante['x_studio_margen_' + str(line.order_id.x_studio_nivel)] if line.product_id.x_fabricante else 12
            id_producto = line.product_id.id
            '''
                Se llena un diccionario para guardar los nuevos precios según el id del producto
            '''
            if line.x_studio_nuevo_costo > 0.0:
                nuevo_precio_minimo = line.x_studio_nuevo_costo/(1 - (margen/100) )
                if id_producto not in dic_nuevos_precios.keys():
                    dic_nuevos_precios.update({id_producto:nuevo_precio_minimo})
                else:
                    if dic_nuevos_precios[id_producto] < nuevo_precio_minimo:
                        dic_nuevos_precios[id_producto] = nuevo_precio_minimo


            '''
                Se llena un diccionario para guardar los cantidades según el id del producto
            '''
            if line.x_cantidad_disponible_compra > 0.0:
                if id_producto not in dic_cantidades_disponibles.keys():
                    dic_cantidades_disponibles.update({id_producto:line.x_cantidad_disponible_compra})
                else:
                    dic_cantidades_disponibles[id_producto] += line.x_cantidad_disponible_compra

        '''
            Validaciones
        '''
        for i,line in enumerate(self.order_line,start=1):
            '''
                Valida que se haya establecido el nuevo precio si se solicito validar datos
            '''

            if line.x_validacion_precio and line.x_studio_nuevo_costo == 0 :
                valid = False
                message += 'No se ha establecido el nuevo costo para el producto' + line.name.replace('\n','') + ' línea(' + str(i) + ')'

            '''
                Validación de cantidades.
                Primero Valida cantidades del valor product.id.virtual_available
                Despues de una validación de parte de compras toma ese valor ingresado por compras en cantidad disponible (Cant. Disponible)
                como producto adicional para surtir productos
            '''
            if line.product_id.virtual_available <= 0.0:
                if line.product_id.id in dic_cantidades_disponibles and dic_cantidades_disponibles[line.product_id.id] < line.product_uom_qty:
                    message += '\n - No hay stock suficiente para el producto: ' + line.name.replace('\n', ' ') + ' línea(' + str(i) + ')'
                    valid = False
                else:
                    if line.product_id.id in dic_cantidades_disponibles.keys():
                        dic_cantidades_disponibles[line.product_id.id]-=line.product_uom_qty
                    else:
                        message += '\n - No hay stock suficiente para el producto: ' + line.name.replace('\n',' ') + ' línea(' + str(i) + ')'
                        valid = False
            else:
                line.product_id.virtual_available-=line.product_uom_qty
            '''
                Validación de nuevo costo
            '''

            # if line.product_id.id in dic_nuevos_precios.keys() and dic_nuevos_precios[line.product_id.id] > line.price_unit:
            #     valid = False
            #     message  += '\n -El precio unitario para producto' + line.name.replace('\n', ' ') + ' no cumple con la utilidad esperada según el nuevo costo.' + ' línea(' + str(i) + ')'

        return valid, message

    def action_confirm_sale(self):
        # registro = self.order_line.filtered(lambda x: x.product_id.virtual_available <= 0).mapped('id')
        # if registro != []:
        #     self.write({'x_aprovar': True, 'state': 'sale_conf'})
        # if registro == []:
        # lines = self.order_line.filtered(lambda x: x.check_price_reduce and not x.price_reduce_solicit)
        # if lines != []:
        #     raise UserError('No se ha enviado la peticion de reducción de precio')
        for order_line in self.order_line:
            if order_line.check_price_reduce:
                raise UserError('No ha solicitado la reducción de precio')
        self.write({'x_aprovar': False})
        total = self.partner_id.credit_rest - self.amount_total
        check = total >= 0 if self.payment_term_id.id != 1 else False
        cliente = self.partner_id.x_studio_triple_a
        facturas = self.partner_id.invoice_ids.filtered(lambda x: x.invoice_date_due != False).filtered(
            lambda x: x.invoice_date_due < fields.date.today() and x.state == 'posted' and x.payment_state in (
            'not_paid', 'partial')).mapped('id')
        #Si es AAA o tiene crédito
        if cliente or check:
            self.write({'x_bloqueo': False, 'x_aprovacion_compras': True})
            return self.action_confirm()
        else:
            self.write({'state': 'credito_conf'})

    def action_view_invoice(self):
        if len(self)==1:
            self.invoice_ids.write({'sale_id': self.id})
        return super(SaleOrder, self).action_view_invoice()

    @api.depends('partner_id', 'partner_child')
    def get_partner(self):
        for record in self:
            res = {}
            group = self.env.ref('sales_team.group_sale_salesman')
            group_s = self.env.ref('sales_team.group_sale_salesman_all_leads')
            grup_ss = self.env.ref('sales_team.group_sale_manager')
            if self.env.user.id in group.users.ids and not self.env.user.id in group_s.users.ids and not self.env.user.id in grup_ss.users.ids:
                partner = self.env['res.partner'].search([['x_nombre_agente_venta', '=', self.env.user.name]])
            else:
                partner = self.env['res.partner'].search([])
            record.partner_loc_ids = [(6,0, partner.ids+partner.mapped('child_ids').ids)]

    # def action_quotation_send(self):
    #     registro = self.order_line.filtered(lambda x: x.product_id.virtual_available <= 0).mapped('id')
    #     if registro:
    #         raise UserError("No hay stock")
    #     else:
    #         return super(SaleOrder, self).action_quotation_send()

    def solicitud_reduccion(self):
        for record in self:
            lines = record.order_line.filtered(lambda x: x.check_price_reduce and not x.price_reduce_solicit)
            if lines:
                self.check_solicitudes = True
            else:
                record.check_solicitudes = False


    def solicitud_reduccion_send(self):
        lines = self.order_line.filtered(lambda x: x.check_price_reduce and not x.price_reduce_solicit)
        mensaje = 'Se solicitará una reduccion de precio de los siguientes productos:\n'
        if lines:
            view = self.env.ref('sale_purchase_confirm.sale_order_alerta_view')
            for row in lines:
                mensaje = mensaje +'Producto: '+ str(row.product_id.name)+' Precio solicitado:'+str(row.price_reduce_v)+'\n'
            wiz = self.env['sale.order.alerta'].create({'sale_id': self.id, 'mensaje': mensaje})
            return {
                'name': _('Alerta'),
                'type': 'ir.actions.act_window',
                'view_mode': 'form',
                'res_model': 'sale.order.alerta',
                'views': [(view.id, 'form')],
                'view_id': view.id,
                'target': 'new',
                'res_id': wiz.id,
                'context': self.env.context,
            }

    def action_confirm(self):
        valid, message = self.is_valid_order_sale()
        if valid:
            r = super(SaleOrder, self).action_confirm()
            self.picking_ids.write({'sale': self.id})
            self.write({'albaran': self.picking_ids.filtered(lambda x: x.picking_type_id.code == 'outgoing' and x.state not in ('cancel', 'draft', 'done'))[0].id})
            return r
        else:
            raise UserError(message)


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'
    existencia = fields.Char('Cantidades', compute='get_stock')
    check_price_reduce = fields.Boolean('Solicitud', default=False, store=True, compute='_compute_check_price_reduce')
    price_reduce_v = fields.Float('Precio solicitado')
    price_reduce_solicit = fields.Boolean('Solicitud', default=False)
    invoice = fields.Boolean('Facturar', default=False)
    price_unit = fields.Float(copy=True)



    def get_valor_minimo(self):
        valor = 0
        for line in self:
            if line.order_id.x_studio_nivel:
                margen = line.product_id.x_fabricante['x_studio_margen_' + str(line.order_id.x_studio_nivel)] if line.product_id.x_fabricante else 12
            else:
                #margen = 12
                raise UserError("Falta definir el nivel en el cliente")
            if line.x_studio_nuevo_costo > 0:
                valor = line.x_studio_nuevo_costo / ((100 - margen) / 100)
            else:
                valor = line.product_id.standard_price / ((100 - margen) / 100)
        return valor

    @api.depends('price_unit')
    def _compute_check_price_reduce(self):
        for record in self:
            if record.order_id.x_studio_nivel:
                margen = record.product_id.x_fabricante['x_studio_margen_' + str(record.order_id.x_studio_nivel)] if record.product_id.x_fabricante else 12
                valor = record.product_id.standard_price / ((100 - margen) / 100)
            else:
                # margen = 12
                # valor = record.product_id.standard_price / ((100 - margen) / 100)
                raise UserError("Falta definir el nivel en el cliente")
            if valor <= record.price_unit:
                record.check_price_reduce = False
                record.price_reduce_v = 0.0
            else:
                record.price_reduce_v = record.price_unit
                record.check_price_reduce = True

    @api.onchange('product_id')
    def product_id_change(self):
        r = super(SaleOrderLine, self).product_id_change()
        self.limit_price()
        return r

    @api.onchange('product_uom', 'product_uom_qty')
    def product_uom_change(self):
        r = super(SaleOrderLine, self).product_uom_change()
        self.limit_price()
        return r

    # @api.onchange('x_studio_nuevo_costo')
    # def _on_change_nuevo_costo(self):
    #     for record in self:
    #         if record.product_id:
    #             margen = record.product_id.x_fabricante[
    #                 'x_studio_margen_' + str(record.order_id.x_studio_nivel)] if record.product_id.x_fabricante else 12
    #             valor = record.x_studio_nuevo_costo / ((100 - margen) / 100)
    #             record.price_unit = round(valor + .5)

    #@api.onchange('price_unit')
    def limit_price(self):
        for record in self:
            valor = 0
            if record.product_id:
                if record.order_id.x_studio_nivel:
                    margen = record.product_id.x_fabricante['x_studio_margen_' + str(record.order_id.x_studio_nivel)] if record.product_id.x_fabricante else 12
                    valor = record.product_id.standard_price / ((100 - margen) / 100)
                else:
                    margen = 12
                    valor = record.product_id.standard_price / ((100 - margen) / 100)
                if valor != 0:
                    if valor < record.price_unit:
                        record.update({'price_unit': round(record.price_unit + .5), 'check_price_reduce': False})
                    else:
                        # record.update({'price_unit': round(valor+ .5), 'price_reduce_v': record.price_unit, 'check_price_reduce': True})
                        record.update({'price_unit': round(valor+ .5)})
                '''
                Parche temporal para evitar que los productos cambien de precio al agregar
                #valias lineas del mismo producto en la misma cotización
                '''
                record.product_id.update({'lst_price': 0})
            record['x_nuevo_precio'] = round(valor + .5)

    @api.depends('product_id')
    def get_stock(self):
        for record in self:
            existencia = ""
            if record.product_id:
                zero = sum(record.product_id.stock_quant_ids.filtered(lambda x: x.location_id.id == 187).mapped('available_quantity'))
                zero1 = sum(record.product_id.stock_quant_ids.filtered(lambda x: x.location_id.id == 187).mapped('reserved_quantity'))
                # one=sum(record.product_id.stock_quant_ids.filtered(lambda x:x.location_id.id==18).mapped('available_quantity'))
                market = sum(record.product_id.stock_quant_ids.filtered(lambda x: x.location_id.id == 80).mapped('available_quantity'))
                market1 = sum(record.product_id.stock_quant_ids.filtered(lambda x: x.location_id.id == 80).mapped('reserved_quantity'))
                existencia = "<table><thead><tr><th>A-0</th><th>A14</th></tr><tr><th>D/R</th><th>D/R</th></tr></thead><tbody><tr><td>" + str(int(zero)) + "/" + str(int(zero1)) + "</td><td>" + str(int(market)) + "/" + str(int(market1)) + "</td></tr></tbody>"
            record.existencia = existencia


class AccountMoveReversal(models.TransientModel):
    _inherit = 'account.move.reversal'

    def reverse_moves(self):
        r = super(AccountMoveReversal, self).reverse_moves()
        move = self.env['account.move'].browse(r['res_id'])
        move.write({'reason': self.reason})
        return r


class SaleAdvancePaymentInv(models.TransientModel):
    _inherit = "sale.advance.payment.inv"

    # def create_invoices(self):
    #     sale_orders = self.env['sale.order'].browse(self._context.get('active_ids', []))
    #     validacion = False
    #     for line in sale_orders.order_line:
    #         if line.product_id.virtual_available > 0:
    #             validacion = True
    #     if validacion:
    #         super(SaleAdvancePaymentInv, self).create_invoices()
    #     else:
    #         raise UserError('No hay stock')


class Alerta_limite_de_credito(models.TransientModel):
    _name = 'sale.order.alerta'
    _description = 'Alerta para reduccion de precio'

    sale_id = fields.Many2one('sale.order', 'Pedido de venta relacionado')
    mensaje = fields.Text('Mensaje')

    def confirmar_sale(self):
        self.sale_id.order_line.filtered(lambda x: x.check_price_reduce).write({'price_reduce_solicit': True})
        # self.env['sale.order'].browse(self.env.context.get('active_ids')).write({'state': 'sale_conf'})
        self.sale_id.order_line.order_id.update({'state': 'sale_conf'})
        mensaje = 'Se redujo el precio del producto '
        for order_line in self.sale_id.order_line:
            if order_line.price_reduce_v >0.0:
                mensaje +=  order_line.product_id.name + ' de $' + str(round(order_line.get_valor_minimo()+.5)) + ' a $'  + str(round(order_line.price_unit +.5)) + '. '
        self.sale_id.message_post(body=mensaje ,type="notification")


class SaleInvoice(models.TransientModel):
    _name = 'sale.orders.invoice'
    _description = 'Wizard de facturacion'
    name = fields.Char()
    sale_ids = fields.Many2many('sale.order', store=True)
    order_lines_ids = fields.One2many('sale.line.wizar', 'rel_id')

    def get_filtered_record(self):
        ordenes = self.env['sale.order'].browse(self.env.context.get('active_ids')).filtered(lambda x: x.state in ('sale', 'done'))
        reg = self.create({'sale_ids': [(6,0,ordenes.ids)]})
        for sale_line in ordenes.mapped('order_line'):
            if sale_line.qty_invoiced != sale_line.product_uom_qty:
                self.env['sale.line.wizar'].create({'rel_id': reg.id, 'sale_line_id': sale_line.id})
        view = self.env.ref('sale_purchase_confirm.sale_order_invoice_conf_view')
        return {
            "name": _("Facturar"),
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": "sale.orders.invoice",
            "views": [(view.id, "form")],
            "view_id": view.id,
            "target": "new",
            "res_id": reg.id,
            "context": self.env.context,
        }

    def confir(self):
        valor = self.order_lines_ids.filtered(lambda x: x.check == True)
        ordenes = self.env['sale.order'].browse(self.env.context.get('active_ids')).filtered(lambda x: x.state in ('sale', 'done'))
        if len(ordenes.mapped('partner_id')) > 1:
            raise UserError("No se puede crear la factura con diferentes clientes")
        else:
            if valor:
                invoice_vals = self.sale_ids[0]._prepare_invoice() if len(self.sale_ids)>1 else self.sale_ids._prepare_invoice()
                invoice_line_vals = []
                for line in valor:
                    data = line.sale_line_id._prepare_invoice_line()
                    data['quantity'] = line.qty_invoice
                    invoice_vals['invoice_line_ids'] += [(0, 0, data)]
                moves = self.env['account.move'].sudo().with_context(default_move_type='out_invoice').create(invoice_vals)
                for move in moves:
                    move.message_post_with_view('mail.message_origin_link',
                                                values={'self': move,
                                                        'origin': move.line_ids.mapped('sale_line_ids.order_id')},
                                                subtype_id=self.env.ref('mail.mt_note').id
                                                )
                if moves:
                    return self.sale_ids[0].action_view_invoice()
        return True


class SaleInvoiceWizard(models.TransientModel):
    _name = 'sale.line.wizar'
    sale_line_id = fields.Many2one('sale.order.line')
    order_id = fields.Many2one(related='sale_line_id.order_id')
    product_id = fields.Many2one(related='sale_line_id.product_id')
    qty = fields.Float(related='sale_line_id.product_uom_qty', string='Cantidad Solicitada')
    qty_sale_invoice = fields.Float(related='sale_line_id.qty_invoiced', string='Cantidad Facturada')
    qty_invoice = fields.Float('Cantidad a Facturar')
    rel_id = fields.Many2one('sale.orders.invoice')
    check = fields.Boolean('Facturar', default=False)

class ProposalState(models.Model):
    _name = 'proposal.state'
    name = fields.Char()

class ProductInherit(models.Model):
    _inherit = 'product.product'
    stock_quant_warehouse_zero = fields.Float(string='Cantidad disponible en almacén 0', compute='_compute_stock_quant_warehouse_zero')

    def _compute_stock_quant_warehouse_zero(self):
        for record in self:
            record.stock_quant_warehouse_zero = sum(record.stock_quant_ids.filtered(lambda x: x.location_id.id == 187).mapped('available_quantity'))


