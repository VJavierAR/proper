# -*- coding: utf-8 -*-
from odoo import api, models, fields, tools, _
from odoo.tools.float_utils import float_round
from xml.dom.minidom import parse, parseString
import logging
import re
from datetime import datetime
from lxml import etree



_logger = logging.getLogger(__name__)
EQUIVALENCIADR_PRECISION_DIGITS = 10
class AccountEdiFormat(models.Model):
    _inherit = 'account.edi.format'

    def get_netting_values(self, move):
        def get_tax_cfdi_name(tax_detail_vals):
            tags = set()
            for detail in tax_detail_vals['group_tax_details']:
                for tag in detail['tax_repartition_line_id'].tag_ids:
                    tags.add(tag)
            tags = list(tags)
            if len(tags) == 1:
                return {'ISR': '001', 'IVA': '002', 'IEPS': '003'}.get(tags[0].name)
            elif tax_detail_vals['tax'].l10n_mx_tax_type == 'Exento':
                return '002'
            else:
                return None

        def divide_tax_details(invoice, tax_details, amount_paid):
            percentage_paid = amount_paid / invoice.amount_total
            precision = invoice.currency_id.decimal_places
            sign = -1 if invoice.is_inbound() else 1
            for detail in tax_details['tax_details'].values():
                tax = detail['tax']
                tax_amount = abs(tax.amount) / 100.0 if tax.amount_type != 'fixed' else abs(detail['tax_amount_currency'] / detail['base_amount_currency'])
                base_val_proportion = float_round(detail['base_amount_currency'] * percentage_paid * sign, precision)
                tax_val_proportion = float_round(base_val_proportion * tax_amount, precision)
                detail.update({
                    'base_val_prop_amt_curr': base_val_proportion,
                    'tax_val_prop_amt_curr': tax_val_proportion if tax.l10n_mx_tax_type != 'Exento' else False,
                    'tax_class': get_tax_cfdi_name(detail),
                    'tax_amount': tax_amount,
                })
            return tax_details


        total_amount = move.amount_total
        currency = move.currency_id

        # Process reconciled invoices.
        invoice_vals_list = []
        pay_rec_lines = move.line_ids.filtered(lambda line: line.account_internal_type in ('receivable'))
        paid_amount = abs(sum(pay_rec_lines.mapped('amount_currency')))

        mxn_currency = self.env["res.currency"].search([('name', '=', 'MXN')], limit=1)
        if move.currency_id == mxn_currency:
            rate_payment_curr_mxn = None
            paid_amount_comp_curr = paid_amount
        else:
            rate_payment_curr_mxn = move.currency_id._convert(1.0, mxn_currency, move.company_id, move.date, round=False)
            paid_amount_comp_curr = move.company_currency_id.round(paid_amount * rate_payment_curr_mxn)

        for field1, field2 in (('debit', 'credit'), ('credit', 'debit')):
            for partial in pay_rec_lines[f'matched_{field1}_ids']:
                payment_line = partial[f'{field2}_move_id']
                invoice_line = partial[f'{field1}_move_id']
                invoice_amount = partial[f'{field1}_amount_currency']
                exchange_move = invoice_line.full_reconcile_id.exchange_move_id
                invoice = invoice_line.move_id

                if not invoice.l10n_mx_edi_cfdi_request:
                    continue

                if exchange_move:
                    exchange_partial = invoice_line[f'matched_{field2}_ids']\
                        .filtered(lambda x: x[f'{field2}_move_id'].move_id == exchange_move)
                    if exchange_partial:
                        invoice_amount += exchange_partial[f'{field2}_amount_currency']

                if invoice_line.currency_id == payment_line.currency_id:
                    # Same currency
                    amount_paid_invoice_curr = invoice_amount
                    exchange_rate = None
                else:
                    # It needs to be how much invoice currency you pay for one payment currency
                    amount_paid_invoice_comp_curr = payment_line.company_currency_id.round(
                        total_amount * (partial.amount / paid_amount_comp_curr))
                    invoice_rate = abs(invoice_line.amount_currency) / abs(invoice_line.balance)
                    amount_paid_invoice_curr = invoice_line.currency_id.round(partial.amount * invoice_rate)
                    exchange_rate = amount_paid_invoice_curr / amount_paid_invoice_comp_curr
                    exchange_rate = float_round(exchange_rate, precision_digits=EQUIVALENCIADR_PRECISION_DIGITS, rounding_method='UP')

                # for CFDI 4.0
                cfdi_values = self._l10n_mx_edi_get_invoice_cfdi_values(invoice)
                tax_details_transferred = divide_tax_details(invoice, cfdi_values['tax_details_transferred'], amount_paid_invoice_curr)
                tax_details_withholding = divide_tax_details(invoice, cfdi_values['tax_details_withholding'], amount_paid_invoice_curr)

                invoice_vals_list.append({
                    'invoice': invoice,
                    'exchange_rate': exchange_rate,
                    'EQUIVALENCIADR_PRECISION_DIGITS': EQUIVALENCIADR_PRECISION_DIGITS,
                    'payment_policy': invoice.l10n_mx_edi_payment_policy,
                    'number_of_payments': len(invoice._get_reconciled_invoices_partials()),
                    'amount_paid': amount_paid_invoice_curr,
                    'amount_before_paid': min(invoice.amount_residual + amount_paid_invoice_curr, invoice.amount_total),
                    'tax_details_transferred': tax_details_transferred,
                    'tax_details_withholding': tax_details_withholding,
                    **self._l10n_mx_edi_get_serie_and_folio(invoice),
                })

        payment_method_code = move.l10n_mx_edi_payment_method_id.code
        is_payment_code_emitter_ok = payment_method_code in ('02', '03', '04', '05', '06', '28', '29', '99')
        is_payment_code_receiver_ok = payment_method_code in ('02', '03', '04', '05', '28', '29', '99')
        is_payment_code_bank_ok = payment_method_code in ('02', '03', '04', '28', '29', '99')

        bank_accounts = move.partner_id.commercial_partner_id.bank_ids.filtered(lambda x: x.company_id.id in (False, move.company_id.id))

        partner_bank = bank_accounts[:1].bank_id
        if partner_bank.country and partner_bank.country.code != 'MX':
            partner_bank_vat = 'XEXX010101000'
        else:  # if no partner_bank (e.g. cash payment), partner_bank_vat is not set.
            partner_bank_vat = partner_bank.l10n_mx_edi_vat

        payment_account_ord = re.sub(r'\s+', '', bank_accounts[:1].acc_number or '') or None
        payment_account_receiver = re.sub(r'\s+', '', move.journal_id.bank_account_id.acc_number or '') or None

        # CFDI 4.0: prepare the tax summaries
        rate_payment_curr_mxn_40 = rate_payment_curr_mxn or 1
        total_taxes_paid = {}
        total_taxes_withheld = {
            '001': {'amount_curr': 0.0, 'amount_mxn': 0.0},
            '002': {'amount_curr': 0.0, 'amount_mxn': 0.0},
            '003': {'amount_curr': 0.0, 'amount_mxn': 0.0},
            None: {'amount_curr': 0.0, 'amount_mxn': 0.0},
        }
        for inv_vals in invoice_vals_list:
            wht_detail = list(inv_vals['tax_details_withholding']['tax_details'].values())
            trf_detail = list(inv_vals['tax_details_transferred']['tax_details'].values())
            for detail in wht_detail + trf_detail:
                tax = detail['tax']
                tax_class = detail['tax_class']
                key = (float_round(tax.amount / 100, 6), tax.l10n_mx_tax_type, tax_class)
                base_val_pay_curr = detail['base_val_prop_amt_curr'] / (inv_vals['exchange_rate'] or 1.0)
                tax_val_pay_curr = detail['tax_val_prop_amt_curr'] / (inv_vals['exchange_rate'] or 1.0)
                if key in total_taxes_paid:
                    total_taxes_paid[key]['base_value'] += base_val_pay_curr
                    total_taxes_paid[key]['tax_value'] += tax_val_pay_curr
                elif tax.amount >= 0:
                    total_taxes_paid[key] = {
                        'base_value': base_val_pay_curr,
                        'tax_value': tax_val_pay_curr,
                        'tax_amount': float_round(detail['tax_amount'], 6),
                        'tax_type': tax.l10n_mx_tax_type,
                        'tax_class': tax_class,
                        'tax_spec': 'W' if tax.amount < 0 else 'T',
                    }
                else:
                    total_taxes_withheld[tax_class]['amount_curr'] += tax_val_pay_curr

        # CFDI 4.0: rounding needs to be done after all DRs are added
        # We round up for the currency rate and down for the tax values because we lost a lot of time to find out
        # that Finkok only accepts it this way.  The other PACs accept either way and are reasonable.
        # To prevent floating point errors we first do a classic round with high precision
        for v in total_taxes_paid.values():
            v['base_value'] = float_round(v['base_value'], 10)
            v['base_value'] = float_round(v['base_value'], move.currency_id.decimal_places, rounding_method='DOWN')
            v['tax_value'] = float_round(v['tax_value'], 10)
            v['tax_value'] = float_round(v['tax_value'], move.currency_id.decimal_places, rounding_method='DOWN')
            v['base_value_mxn'] = float_round(v['base_value'] * rate_payment_curr_mxn_40, mxn_currency.decimal_places)
            v['tax_value_mxn'] = float_round(v['tax_value'] * rate_payment_curr_mxn_40, mxn_currency.decimal_places)
        for v in total_taxes_withheld.values():
            v['amount_curr'] = float_round(v['amount_curr'], 10)
            v['amount_curr'] = float_round(v['amount_curr'], move.currency_id.decimal_places, rounding_method='DOWN')
            v['amount_mxn'] = float_round((v['amount_curr'] + 150) * rate_payment_curr_mxn_40, mxn_currency.decimal_places)

        cfdi_values = {
            **self._l10n_mx_edi_get_common_cfdi_values(move),
            'invoice_vals_list': invoice_vals_list,
            'currency': currency,
            'amount': total_amount,
            'amount_mxn': float_round((total_amount  + 150) * rate_payment_curr_mxn_40, mxn_currency.decimal_places),
            'rate_payment_curr_mxn': rate_payment_curr_mxn,
            'rate_payment_curr_mxn_40': rate_payment_curr_mxn_40,
            'emitter_vat_ord': is_payment_code_emitter_ok and partner_bank_vat,
            'bank_vat_ord': is_payment_code_bank_ok and partner_bank.name,
            'payment_account_ord': is_payment_code_emitter_ok and payment_account_ord,
            'receiver_vat_ord': is_payment_code_receiver_ok and move.journal_id.bank_account_id.bank_id.l10n_mx_edi_vat,
            'payment_account_receiver': is_payment_code_receiver_ok and payment_account_receiver,
            'cfdi_date': move.l10n_mx_edi_post_time.strftime('%Y-%m-%dT%H:%M:%S'),
            'tax_summary': total_taxes_paid,
            'withholding_summary': total_taxes_withheld,
        }

        cfdi_payment_datetime = datetime.combine(fields.Datetime.from_string(move.date), datetime.strptime('12:00:00', '%H:%M:%S').time())
        cfdi_values['cfdi_payment_date'] = cfdi_payment_datetime.strftime('%Y-%m-%dT%H:%M:%S')

        if cfdi_values['customer'].country_id.l10n_mx_edi_code != 'MEX':
            cfdi_values['customer_fiscal_residence'] = cfdi_values['customer'].country_id.l10n_mx_edi_code
        else:
            cfdi_values['customer_fiscal_residence'] = None

        return cfdi_values


    def _l10n_mx_edi_append_compensate_node(self, cfdi_str, move,cfdi_values):
        dom = parseString(cfdi_str)
        totales = dom.getElementsByTagName('pago20:Totales')[0]
        nodos_pago = dom.getElementsByTagName("pago20:Pago")
        nodos_impuesto = dom.getElementsByTagName("pago20:TrasladoDR")
        nodos_docto_relacionado = dom.getElementsByTagName('pago20:DoctoRelacionado')
        suma_traslados_base_iva16 = 0.0
        suma_traslados_impuesto_iva16 = 0.0
        suma_totales = 0.0
        for node in nodos_pago:
            suma_totales += float(node.getAttribute('Monto'))
        for node in nodos_impuesto:
            suma_traslados_base_iva16 += float(node.getAttribute('BaseDR'))
            suma_traslados_impuesto_iva16 += float(node.getAttribute('ImporteDR'))
        for i, docto_relacionado in enumerate(nodos_docto_relacionado):
            for j in range(i+1, len(nodos_docto_relacionado)):
                if docto_relacionado.getAttribute('IdDocumento') == nodos_docto_relacionado[j].getAttribute('IdDocumento'):
                    num_parcialidad = int(nodos_docto_relacionado[j].getAttribute('NumParcialidad')) - 1
                    total = float(docto_relacionado.getAttribute('ImpSaldoAnt')) + float(nodos_docto_relacionado[j].getAttribute('ImpPagado'))
                    docto_relacionado.setAttribute('NumParcialidad', str(num_parcialidad))
                    docto_relacionado.setAttribute('ImpSaldoAnt', str(round(total,2)))
                    docto_relacionado.setAttribute('ImpSaldoInsoluto', str(
                        round(float(docto_relacionado.getAttribute('ImpSaldoAnt')) - float(docto_relacionado.getAttribute('ImpPagado')),2)
                    ))
                    break


        totales.setAttribute('MontoTotalPagos',str(round(suma_totales,2)))
        if round(suma_traslados_base_iva16,2) > 0.0:
            totales.setAttribute('TotalTrasladosBaseIVA16',str(round(suma_traslados_base_iva16,2)))
            totales.setAttribute('TotalTrasladosImpuestoIVA16', str(round(suma_traslados_impuesto_iva16,2)))
        cfdi = dom.toxml()
        decoded_cfdi_values = move._l10n_mx_edi_decode_cfdi(cfdi_data=cfdi)
        cfdi_cadena_crypted = cfdi_values['certificate'].sudo().get_encrypted_cadena(decoded_cfdi_values['cadena'])
        decoded_cfdi_values['cfdi_node'].attrib['Sello'] = cfdi_cadena_crypted
        return etree.tostring(decoded_cfdi_values['cfdi_node'], pretty_print=True, xml_declaration=True, encoding='UTF-8')
        # return dom.toxml().encode('utf-8')


    def _l10n_mx_edi_export_payment_cfdi(self, move):
        r = super(AccountEdiFormat, self)._l10n_mx_edi_export_payment_cfdi(move)
        '''
            Insertar los nodos del pago por compensación aquí

        '''
        pago = self.env['account.payment'].search([('move_id', '=', move.id)])
        neteo = self.env['account.move'].search([('rel_payment', '=', pago.id)])
        if neteo:
            template_pago = self.env.ref('factoraje_financiero.pagocompensacion')
            cfdi_values = self.get_netting_values(neteo)
            cfdi_values.update({'l10n_mx_edi_payment_method_id':self.env['l10n_mx_edi.payment.method'].browse(12), 'tax_objected': move._l10n_mx_edi_get_tax_objected()})
            pago_str = template_pago._render(cfdi_values)
            s = r['cfdi_str'].decode()
            io = s.index('</pago20:Pagos>')
            fp = s[:io]
            lp = s[io:]
            rd = fp.encode('utf-8') + pago_str.encode('utf-8') + lp.encode('utf-8')
            r['cfdi_str'] = rd
            r['cfdi_str'] = self._l10n_mx_edi_append_compensate_node(r['cfdi_str'], move,cfdi_values)
        return r