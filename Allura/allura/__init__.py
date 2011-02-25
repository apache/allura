# -*- coding: utf-8 -*-
"""The allura package"""
from paste.registry import StackedObjectProxy

credentials = StackedObjectProxy(name='credentials')
carrot_connection = StackedObjectProxy(name='carrot_connection')
