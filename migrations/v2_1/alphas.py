from Acquisition import aq_base
from Products.CMFPlone.migrations.migration_util import installOrReinstallProduct


def two05_alpha1(portal):
    """2.0.5 -> 2.1-alpha1
    """
    out = []

    # Install SecureMailHost
    replaceMailHost(portal, out)

    # Remove legacy tools
    deleteTool(portal, out, 'portal_form')
    deleteTool(portal, out, 'portal_navigation')

    # Remove old properties
    deletePropertySheet(portal, out, 'form_properties')
    deletePropertySheet(portal, out, 'navigation_properties')

    # Install Archetypes and ATCT
    installArchetypes(portal, out)
    installATContentTypes(portal, out)

    # Switch over to ATCT
    migrateToATCT(portal, out)

    return out


def replaceMailHost(portal, out):
    """Replaces the mailhost with a secure mail host."""
    id = 'MailHost'
    oldmh = getattr(aq_base(portal), id)
    title = oldmh.title
    smtp_host = oldmh.smtp_host
    smtp_port = oldmh.smtp_port
    portal.manage_delObjects([id])
    out.append('Removed old MailHost')

    addMailhost = portal.manage_addProduct['SecureMailHost'].manage_addMailHost
    addMailhost(id, title=title, smtp_host=smtp_host, smtp_port=smtp_port)
    out.append('Added new MailHost (SecureMailHost): %s:%s' % (smtp_host, smtp_port))


def deleteTool(portal, out, tool_name):
    """Deletes a tool."""
    if hasattr(aq_base(portal), tool_name):
        portal._delObject(tool_name)
    out.append('Deleted %s tool.' % tool_name)


def deletePropertySheet(portal, out, sheet_name):
    """Deletes a property sheet from portal_properties."""
    proptool = portal.portal_properties
    if hasattr(aq_base(proptool), sheet_name):
        proptool._delObject(sheet_name)
    out.append('Deleted %s property sheet.' % sheet_name)


def installArchetypes(portal, out):
    """Quickinstalls Archetypes if not installed yet."""
    for product_name in ('MimetypesRegistry', 'PortalTransforms', 'Archetypes'):
        installOrReinstallProduct(portal, product_name, out)


def installATContentTypes(portal, out):
    """Quickinstalls ATContentTypes if not installed yet."""
    for product_name in ('ATContentTypes',):
        installOrReinstallProduct(portal, product_name, out)


def migrateToATCT(portal, out):
    """Switches portal to ATContentTypes."""
    get_transaction().commit(1)
    migrateFromCMFtoATCT = portal.migrateFromCMFtoATCT
    switchCMF2ATCT = portal.switchCMF2ATCT
    #out.append('Migrating and switching to ATContentTypes ...')
    result = migrateFromCMFtoATCT()
    out.append(result)
    try:
        switchCMF2ATCT(skip_rename=False)
    except IndexError:
        switchCMF2ATCT(skip_rename=True)
    get_transaction().commit(1)
    #out.append('Switched portal to ATContentTypes.')

