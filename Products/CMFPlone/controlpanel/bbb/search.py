from zope.site.hooks import getSite
from Products.CMFPlone.interfaces.siteroot import IPloneSiteRoot
from zope.component import adapts
from zope.interface import implements
from Products.CMFPlone.interfaces import ISearchSchema
from Products.CMFCore.utils import getToolByName
from zope.component import getUtility
from plone.registry.interfaces import IRegistry


class SearchControlPanelAdapter(object):

    adapts(IPloneSiteRoot)
    implements(ISearchSchema)

    def __init__(self, context):
        self.portal = getSite()
        self.jstool = getToolByName(context, 'portal_javascripts')
        registry = getUtility(IRegistry)
        self.search_settings = registry.forInterface(
            ISearchSchema, prefix="plone")

    def get_enable_livesearch(self):
        return self.search_settings.enable_livesearch

    def set_enable_livesearch(self, value):
        if value:
            self.search_settings.enable_livesearch = True
            #self.jstool.getResource('livesearch.js').setEnabled(True)
        else:
            self.search_settings.enable_livesearch = False
            #self.jstool.getResource('livesearch.js').setEnabled(False)
        self.jstool.cookResources()

    enable_livesearch = property(get_enable_livesearch, set_enable_livesearch)

    def get_types_not_searched(self):
        return self.search_settings.types_not_searched

    def set_types_not_searched(self, value):
        self.search_settings.types_not_searched = value

    types_not_searched = property(
        get_types_not_searched,
        set_types_not_searched
    )
