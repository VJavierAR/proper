from odoo import models, fields,api, _


class RequerimientClient(models.Model):
    _name = 'requiriment.client'
    x_cantidad = fields.Float("cantidad")
    x_comprar = fields.Boolean("Comprar")
    x_count = fields.Integer("count", compute='set_count')
    x_descripcion = fields.Char("Descripcion")
    x_lines_proposal = fields.One2many("proposal.purchases", 'rel_id', "Propuestas")
    x_link_sitio = fields.Char("Link producto")
    x_marca = fields.Char("Marca")
    x_modelo = fields.Char("Modelo")
    x_name = fields.Char("Name")
    x_order_id = fields.Many2one("sale.order", 'Orden')
    x_precio_uni = fields.Float("Precio unitario")
    x_presupuesto = fields.Float("presupuesto")
    x_proveedor = fields.Char("proveedor")
    x_studio_estado = fields.Selection([('open', 'open'), ('closed', 'closed'), ('cancel', 'cancel')], "Estado")
    x_studio_related_field_1eaGE = fields.Char("Cliente", related='x_order_id.partner_id.name')
    x_studio_related_field_DGJgC = fields.Char("New Campo relacionado", related='x_order_id.company_id.display_name')
    x_studio_related_field_ap2ah = fields.Char("Vendedor", related='x_order_id.user_id.display_name')

    @api.model
    def create(self, vals):
        vals['x_name'] = self.env['ir.sequence'].next_by_code('requiriment.seq') or _('New')
        return super(RequerimientClient, self).create(vals)


    @api.depends('x_lines_proposal')
    def set_count(self):
        for record in self:
            record.x_count= len(record.x_lines_proposal)


    def create_proposal(self):
        view = self.env.ref('sale_purchase_confirm.wizard_proposal_form_view')
        wiz = self.env['wizard.proposal'].create({'x_rel_id': self.id})
        return {
            'name': 'Propuesta',
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'wizard.proposal',
            'views': [(view.id, 'form')],
            'view_id': view.id,
            'target': 'new',
            'res_id': wiz.id,
            'context': self.env.context}

    def view_proposal(self):
        action = self.env.ref('sale_purchase_confirm.action_proposal_purchase').read()[0]
        lines = self.x_lines_proposal.mapped('id')
        action['domain'] = [('id', 'in', lines)]
        return action

    def cancel(self):
        self.x_studio_estado = 'cancel'

class ProposalPurchase(models.Model):
    _inherit = 'mail.thread'
    _name = 'proposal.purchases'
    rel_id = fields.Many2one('requiriment.client')
    x_agente_compra = fields.Char("Agente de compra")
    x_archivo = fields.Binary("Archivo")
    x_cantidad = fields.Float("Cantidad")
    x_caracteristicas = fields.Text("Caracteristicas")
    x_categoria_id = fields.Many2one("product.category", "Categoría")
    x_condiciones_de_pago = fields.Char("Condiciones de Pago")
    x_costo = fields.Float("costo")
    x_descripcion = fields.Char("Descripción")
    x_detalle = fields.Char("Detalle", compute='get_detalle')
    x_documento = fields.Binary("Documento")
    x_garantias = fields.Text("Garantias")
    x_iva = fields.Boolean("IVA")
    x_marca = fields.Char("Marca")
    x_modelo = fields.Char("Modelo")
    x_motivo_cancelacion = fields.Char("Motivo de Cancelación")
    x_name = fields.Char("Name")
    x_new_prod_prop = fields.Boolean("Producto de propuesta")
    x_notas = fields.Text("Notas")
    x_note = fields.Text("Notas")
    x_pro_aten = fields.Selection([('yes', 'SI'), ('no', 'NO')], "Propuesta Atendida")
    x_product_id = fields.Many2one("product.product", "producto")
    x_proveedor = fields.Many2one("res.partner", "proveedor")
    x_state = fields.Selection([('draft', 'Borrador'), ('done', 'Propuesta Aceptada'), ('cancel', 'Cancelado'), ('validar', 'Re-Validar'), ('atendido', 'Atenidod'), ('confirm', 'Compra Autorizada')],"estado", default='draft')
    x_studio_aprovacin_de_compras = fields.Boolean("Aprovación de Compras", related='rel_id.x_order_id.x_aprovacion_compras')
    x_studio_archivo = fields.Binary("Archivo")
    x_studio_archivo_filename = fields.Char("Filename for x_studio_binary_field_kkNkg")
    x_studio_estado_de_cotizacin = fields.Selection(related="rel_id.x_order_id.state", string="Estado de la cotizacion")
    x_studio_integer_field_Olr5a = fields.Integer("New Entero")
    x_studio_proveedor = fields.Char("Proveedor")
    x_studio_related_field_gKx5P = fields.Char("Orden de venta", related="rel_id.x_order_id.display_name")
    x_studio_revalidacion = fields.Char("Motivo de revalidación")
    x_studio_text_field_GWDee = fields.Text("Notas")
    x_terminado = fields.Boolean("Regresar propuesta")
    x_tiempo_entrega = fields.Char("Timepo de entrega")
    x_vigencia = fields.Char("Vigencia")
    x_familia_id = fields.Many2one("x_familia", "Familia")
    x_linea_id = fields.Many2one("x_linea", "Línea")
    x_grup_id = fields.Many2one("x_grupo", "Grupo")

    @api.depends('rel_id')
    def get_detalle(self):
        for record in self:
            record.x_detalle = ''
            if record.rel_id.id:
                t = "<table class='table'><tr><td>Nombre</td><td>Descripción</td><td>Marca</td><td>Modelo</td><td>Cantidad</td><td>Presupuesto</td><td>Proveedor</td><td>linkproducto</td></tr>"
                t = t + "<tr><td>" + str(record.rel_id.x_name) + "</td><td>" + str(
                    record.rel_id.x_descripcion) + "</td><td>" + str(record.rel_id.x_marca) + "</td><td>" + str(
                    record.rel_id.x_modelo) + "</td><td>" + str(record.rel_id.x_cantidad) + "</td><td>" + str(
                    record.rel_id.x_presupuesto) + "</td><td>" + str(record.rel_id.x_proveedor) + "</td><td>" + str(
                    record.rel_id.x_link_sitio) + "</td></tr></table>"
                record.x_detalle = t
    @api.model
    def create(self, vals):
        vals['x_name'] = self.env['ir.sequence'].next_by_code('proposal.seq') or _('New')
        return super(ProposalPurchase, self).create(vals)

    def confirm(self):
        self.x_state = 'done'
        if not self.x_product_id.id:
            # marca = env['x_fabricante'].search([['name','=', record.x_marca]])
            marca = False
            self.x_product_id = self.env['product.product'].create(
                {'standard_price': self.x_costo, 'x_studio_ultimo_costo': self.x_costo,
                 'default_code': self.x_modelo, 'type': 'product', 'x_fabricante': marca.id if marca else False,
                 'name': self.x_descripcion, 'description_sale': self.x_caracteristicas,
                 'x_studio_many2one_field_0X3u9': self.x_grup_id.id, 'categ_id': self.x_categoria_id.id,
                 'x_studio_many2one_field_RWuq7': self.x_familia_id.id,
                 'x_studio_many2one_field_LZOP8': self.x_linea_id.id, 'image_1920': self.x_archivo,
                 'x_producto_propuesta': self.x_new_prod_prop})
        self.x_rel_id.x_order_id.write({'order_line': [(0, 0, {'x_studio_nuevo_costo': self.x_costo,
                                                                 'product_id': self.x_product_id.id,
                                                                 'product_uom_qty': self.x_cantidad,
                                                                 'price_unit': self.x_costo / .8 if not self.x_iva else (
                                                                                                                                        (
                                                                                                                                            self.x_costo) * 1.16) / .8,
                                                                 'x_precio_propuesta': self.x_costo / .8 if not self.x_iva else (
                                                                                                                                                (
                                                                                                                                                    self.x_costo) * 1.16) / .8})]})
    def cancel(self):
        self.x_state = 'cancel'
        view = self.env.ref('sale_purchase_confirm.wizard_cancel_form_view')
        wiz = self.env['wizard.cancel'].create({'proposal_id': self.id})
        action = {
            'name': 'Cancelacion de propuesta',
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'wizard.cancel',
            'views': [(view.id, 'form')],
            'view_id': view.id,
            'target': 'new',
            'res_id': wiz.id,
            'context': self.env.context}

    def validar(self):
        self.x_state = 'validar'
        view = self.env.ref()
        wiz = self.env['wizard.revali'].create({'proposal_id': self.id})
        action = {
            'name': 'Revalidar propuesta',
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'wizard.revali',
            'views': [(view.id, 'form')],
            'view_id': view.id,
            'target': 'new',
            'res_id': wiz.id,
            'context': self.env.context}

    def autoriz(self):
        self.x_state = 'confirm'


class WizarPropo(models.TransientModel):
    _name = 'wizard.proposal'
    x_agente_compra = fields.Char("Agente de Compra")
    x_archivo = fields.Binary("Imagen del producto")
    x_archivo_2 = fields.Binary("*Archivo")
    x_cantidad = fields.Char("Cantidad")
    x_caracteristicas = fields.Text("Caracteristicas")
    x_categoria_id = fields.Many2one("product.category", "Categoría")
    x_condiciones_de_pago = fields.Char("Condiciones de Pago")
    x_costo = fields.Float("Costo")
    x_descripcion = fields.Char("Descripción")
    x_detalle = fields.Char("Detalle")
    x_documento = fields.Binary("Documento")
    x_familia_id = fields.Many2one("x_familia", "Familia")
    x_garantias = fields.Text("Garantias")
    x_grup_id = fields.Many2one("x_grupo", "Grupo")
    x_iva = fields.Boolean("IVA")
    x_linea_id = fields.Many2one("x_linea", "Linea")
    x_marca = fields.Char("Marca")
    x_modelo = fields.Char("Modelo")
    x_name = fields.Char("Name")
    x_note = fields.Text("Notas")
    x_product_id = fields.Many2one("product.product", "producto")
    x_proveedor = fields.Many2one("res.partner", "Proveedor")
    x_proveedor_char = fields.Char("Proveedor")
    x_rama = fields.Selection([("SOBREPEDIDO","SOBREPEDIDO"),
                                        ("LINEA","LINEA"),
                                        ("OBSOLETO","OBSOLETO"),
                                        ("DESCONTINUADO","DESCONTINUADO"),
                                        ("CATALOGO","CATALOGO"),
                                        ("ACTIVO FIJO","ACTIVO FIJO"),
                                        ("ADMON","ADMON"),
                                        ("PROMOCION","PROMOCION")], "Rama")
    x_rel_id = fields.Many2one("requiriment.client", "Requerimiento")
    x_tiempo_entrega = fields.Char("Tiempo de entrega")
    x_vigencia = fields.Char("Vigencia")

    def confirm(self):
        self.env['proposal.purchases'].create(
            {'create_uid': self.create_uid.id, 'x_descripcion': self.x_descripcion, 'x_iva': self.x_iva,
             'x_condiciones_de_pago': self.x_condiciones_de_pago, 'x_garantias': self.x_garantias,
             'x_vigencia': self.x_vigencia, 'x_caracteristicas': self.x_caracteristicas,
             'x_tiempo_entrega': self.x_tiempo_entrega, 'x_archivo': self.x_archivo, 'rel_id': self.x_rel_id.id,
             'x_marca': self.x_marca, 'x_grup_id': self.x_grup_id.id, 'x_categoria_id': self.x_categoria_id.id,
             'x_familia_id': self.x_familia_id.id, 'x_linea_id': self.x_linea_id.id, 'x_modelo': self.x_modelo,
             'x_cantidad': self.x_cantidad, 'x_costo': self.x_costo, 'x_studio_proveedor': self.x_proveedor_char,
             'x_documento': self.x_documento, 'x_note': self.x_note})

class WizardCancel(models.TransientModel):
    _name = 'wizard.cancel'
    check = fields.Boolean('Check')
    description = fields.Char('Descripcion')
    proposal_id = fields.Many2one('proposal.purchases')

    def confirm(self):
        self.proposal_id.write({'x_motivo_cancelacion': self.description})

class WizardRevalid(models.TransientModel):
    _name = 'wizard.revali'
    description = fields.Char('Descripcion')
    proposal_id = fields.Many2one('proposal.purchases')

    def confirm(self):
        self.proposal_id.write({'x_studio_revalidacion': self.description})
