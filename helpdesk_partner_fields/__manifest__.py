# -*- coding: utf-8 -*-
{
    'name': "Heldesk Partner Fields",

    'summary': """""",

    'description': """
    Agrega alguno campos a helpdesk
    """,

    'author': "My Company",
    'website': "http://www.yourcompany.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/13.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'contacts', 'helpdesk','stock'],

    # always loaded
    'data': [
        #'security/ir.model.access.csv',
        #'views/views.xml',

    ],
    # only loaded in demonstration mode
    'demo': [

    ],
}
