# -*- coding: utf-8 -*-
{
    'name': "Consolidación de ventas",

    'summary': """
        Consolida las líneas de la orden de venta para crear una factura""",

    'description': """
        Permite consolidar las líneas de la orden de venta y crear una factura a partir de esta
        en el orden seleccionado en el wizard
    """,

    'author': "Jonathan Alfaro",
    'website': "http://www.yourcompany.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/13.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'sale', 'account', 'l10n_mx_edi'],

    # always loaded
    'data': [
        'views/views.xml',
        'wizard/consolidacion_wizard_view.xml',
        'security/ir.model.access.csv'
    ],
}
