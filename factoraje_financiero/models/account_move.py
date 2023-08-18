
from odoo import fields,models, _, api
from datetime import datetime
from odoo.exceptions import UserError

class AccountMove(models.Model):
    _inherit = 'account.move'
    factoring_amount = fields.Float('Monto por factoraje')
    balance_after_factoring = fields.Float(string='Restante', compute='_compute_balance_after_factoring')
    rel_payment = fields.Many2one('account.payment')

    @api.depends('porcent_assign', 'factoring_amount')
    def _compute_balance_after_factoring(self):
        for record in self:
            record.balance_after_factoring = record.amount_residual - record.factoring_amount - record.porcent_assign


    def view_financial_factoring_wizard(self):
        active_ids = self._context.get('active_ids')
        facturas = self.env['account.move'].browse(active_ids)
        facturas.write({'factoring_amount': 0.0, 'porcent_assign': 0.0})
        w = self.env['account.payment.register'].with_context(active_model='account.move', active_ids=active_ids).create({
            'group_payment': True,
            'hide_fields_factoraje': False,
            'partner_bills': facturas,
            'amount': 0.0
        })
        view = self.env.ref('factoraje_financiero.account_payment_register_form_factoring')
        return {
            'name': _('Factoraje'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment.register',
            'view_mode': 'form',
            'res_id': w.id,
            'views': [(view.id, 'form')],
            'view_id': view.id,
            'target': 'new'
        }