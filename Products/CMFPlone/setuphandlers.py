from borg.localrole.utils import replace_local_role_manager

from zope.component import queryUtility
from zope.interface import implements

from Acquisition import aq_base
from Products.CMFCore.utils import getToolByName
from Products.CMFQuickInstallerTool.interfaces import INonInstallable
from Products.StandardCacheManagers.AcceleratedHTTPCacheManager \
    import AcceleratedHTTPCacheManager
from Products.StandardCacheManagers.RAMCacheManager import RAMCacheManager

from Products.CMFPlone.factory import _DEFAULT_PROFILE
from Products.CMFPlone.interfaces import IMigrationTool


class HiddenProducts(object):
    implements(INonInstallable)

    def getNonInstallableProducts(self):
        return [
            'Archetypes', 'Products.Archetypes',
            'CMFDefault', 'Products.CMFDefault',
            'CMFPlone', 'Products.CMFPlone', 'Products.CMFPlone.migrations',
            'CMFTopic', 'Products.CMFTopic',
            'CMFUid', 'Products.CMFUid',
            'DCWorkflow', 'Products.DCWorkflow',
            'PasswordResetTool', 'Products.PasswordResetTool',
            'PlonePAS', 'Products.PlonePAS',
            'wicked.at',
            'PloneLanguageTool', 'Products.PloneLanguageTool',
            'CMFFormController', 'Products.CMFFormController',
            'MimetypesRegistry', 'Products.MimetypesRegistry',
            'PortalTransforms', 'Products.PortalTransforms',
            'CMFDiffTool', 'Products.CMFDiffTool',
            'CMFEditions', 'Products.CMFEditions',
            'Products.NuPlone',
            'plone.portlet.static',
            'plone.portlet.collection',
            'borg.localrole',
            'plone.keyring',
            'plone.outputfilters',
            'plone.protect',
            'plone.app.jquery'
            'plone.app.jquerytools',
            'plone.app.blob',
            'plone.app.discussion',
            'plone.app.folder',
            'plone.app.imaging',
            'plone.app.registry',
            'plone.app.search',
            'plone.app.z3cform',
            ]


def addCacheHandlers(portal):
    """ Add RAM and AcceleratedHTTP cache handlers """
    mgrs = [(AcceleratedHTTPCacheManager, 'HTTPCache'),
            (RAMCacheManager, 'RAMCache'),
            (RAMCacheManager, 'ResourceRegistryCache'),
            ]
    for mgr_class, mgr_id in mgrs:
        existing = portal.get(mgr_id, None)
        if existing is None:
            portal[mgr_id] = mgr_class(mgr_id)
        else:
            unwrapped = aq_base(existing)
            if not isinstance(unwrapped, mgr_class):
                del portal[mgr_id]
                portal[mgr_id] = mgr_class(mgr_id)


def addCacheForResourceRegistry(portal):
    ram_cache_id = 'ResourceRegistryCache'
    if ram_cache_id in portal:
        cache = getattr(portal, ram_cache_id)
        settings = cache.getSettings()
        settings['max_age'] = 24 * 3600  # keep for up to 24 hours
        settings['request_vars'] = ('URL', )
        cache.manage_editProps('Cache for saved ResourceRegistry files',
                               settings)
    reg = getToolByName(portal, 'portal_css', None)
    if reg is not None \
            and getattr(aq_base(reg), 'ZCacheable_setManagerId', None) \
                is not None:
        reg.ZCacheable_setManagerId(ram_cache_id)
        reg.ZCacheable_setEnabled(1)

    reg = getToolByName(portal, 'portal_javascripts', None)
    if reg is not None \
            and getattr(aq_base(reg), 'ZCacheable_setManagerId', None) \
                is not None:
        reg.ZCacheable_setManagerId(ram_cache_id)
        reg.ZCacheable_setEnabled(1)


def setProfileVersion(portal):
    """
    Set profile version.
    """
    mt = queryUtility(IMigrationTool)
    mt.setInstanceVersion(mt.getFileSystemVersion())
    setup = getToolByName(portal, 'portal_setup')
    version = setup.getVersionForProfile(_DEFAULT_PROFILE)
    setup.setLastVersionForProfile(_DEFAULT_PROFILE, version)


def assignTitles(portal):
    titles = {
     'acl_users': 'User / Group storage and authentication settings',
     'archetype_tool': 'Archetypes specific settings',
     'caching_policy_manager': 'Settings related to proxy caching',
     'content_type_registry': 'MIME type settings',
     'error_log': 'Error and exceptions log viewer',
     'MailHost': 'Mail server settings for outgoing mail',
     'mimetypes_registry': 'MIME types recognized by Plone',
     'plone_utils': 'Various utility methods',
     'portal_actions': 'Contains custom tabs and buttons',
     'portal_calendar': 'Controls how events are shown',
     'portal_catalog': 'Indexes all content in the site',
     'portal_controlpanel': 'Registry of control panel screen',
     'portal_css': 'Registry of CSS files',
     'portal_diff': 'Settings for content version comparisions',
     'portal_groupdata': 'Handles properties on groups',
     'portal_groups': 'Handles group related functionality',
     'portal_javascripts': 'Registry of JavaScript files',
     'portal_languages': 'Language specific settings',
     'portal_membership': 'Handles membership policies',
     'portal_memberdata': 'Handles the available properties on members',
     'portal_migration': 'Upgrades to newer Plone versions',
     'portal_password_reset': 'Handles password retention policy',
     'portal_properties': 'General settings registry',
     'portal_quickinstaller': 'Allows to install/uninstall products',
     'portal_registration': 'Handles registration of new users',
     'portal_setup': 'Add-on and configuration management',
     'portal_skins': 'Controls skin behaviour (search order etc)',
     'portal_transforms': 'Handles data conversion between MIME types',
     'portal_types': 'Controls the available content types in your portal',
     'portal_url': 'Methods to anchor you to the root of your Plone site',
     'portal_view_customizations': 'Template customizations',
     'portal_workflow': 'Contains workflow definitions for your portal',
     'reference_catalog': 'Catalog of content references',
     'translation_service': 'Provides access to the translation machinery',
     'uid_catalog': 'Catalog of unique content identifiers',
     }
    for oid, obj in portal.items():
        title = titles.get(oid, None)
        if title:
            setattr(aq_base(obj), 'title', title)


def importFinalSteps(context):
    """
    Final Plone import steps.
    """
    # Only run step if a flag file is present (e.g. not an extension profile)
    if context.readDataFile('plone-final.txt') is None:
        return
    site = context.getSite()
    setProfileVersion(site)

    # Install our dependencies
    st = getToolByName(site, "portal_setup")
    st.runAllImportStepsFromProfile("profile-Products.CMFPlone:dependencies")

    assignTitles(site)
    replace_local_role_manager(site)
    addCacheHandlers(site)
    addCacheForResourceRegistry(site)


def updateWorkflowRoleMappings(context):
    """
    If an extension profile (such as the testfixture one) switches default,
    workflows, this import handler will make sure object security works
    properly.
    """
    # Only run step if a flag file is present
    if context.readDataFile('plone-update-workflow-rolemap.txt') is None:
        return
    site = context.getSite()
    portal_workflow = getToolByName(site, 'portal_workflow')
    portal_workflow.updateRoleMappings()
