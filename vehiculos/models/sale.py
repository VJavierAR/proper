# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.osv import expression

class Sale(models.Model):
    _inherit = 'sale.order'
    carrier_tracking_ref = fields.Char('No de Guia')

    def write(self, values):
        if 'carrier_tracking_ref' in values:
            for pi in self.picking_ids:
                if not pi.carrier_tracking_ref:
                    pi.write({'carrier_tracking_ref': values['carrier_tracking_ref']})
        return super(Sale, self).write(values)