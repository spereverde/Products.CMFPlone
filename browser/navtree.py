# This module contains a function to help build navigation-tree-like structures
# from catalog queries. It also contains a standard implementation of the
# strategy/filtering method that uses Plone's navtree_properties to construct
# navtrees.

from zope.interface import implements

from Acquisition import aq_base

from Products.CMFCore.utils import getToolByName
from Products.CMFPlone import utils
from Products.CMFPlone.browser.interfaces import INavtreeStrategy
from Products.CMFPlone.browser.interfaces import INavigationRoot
from Products.CMFPlone.browser.interfaces import INavigationQueryBuilder

from types import StringType

class NavtreeStrategyBase:
    """Basic navigation tree strategy that does nothing.
    """

    implements(INavtreeStrategy)

    __allow_access_to_unprotected_subobjects__ = 1
    
    rootPath = None
    showAllParents = False

    def nodeFilter(self, node):
        return True

    def subtreeFilter(self, node):
        return True

    def decoratorFactory(self, node):
        return node

def buildFolderTree(context, obj=None, query={}, strategy=NavtreeStrategyBase()):
    """Create a tree structure representing a navigation tree. By default,
    it will create a full "sitemap" tree, rooted at the portal, ordered
    by explicit folder order. If the 'query' parameter contains a 'path'
    key, this can be used to override this. To create a navtree rooted
    at the portal root, set query['path'] to:

        {'query' : '/'.join(context.getPhysicalPath()),
         'navtree' : 1}

    to start this 1 level below the portal root, set query['path'] to:

        {'query' : '/'.join(obj.getPhysicalPath()),
         'navtree' : 1,
         'navtree_start' : 1}

    to create a sitemap with depth limit 3, rooted in the portal:

        {'query' : '/'.join(obj.getPhysicalPath()),
         'depth' : 3}

    The parameters:

    - 'context' is the acquisition context, from which tools will be acquired
    - 'obj' is the current object being displayed.
    - 'query' is a catalog query to apply to find nodes in the tree.
    - 'strategy' is an object that can affect how the generation works. It
        should be derived from NavtreeStrategyBase, if given, and contain:

            rootPath -- a string property; the physical path to the root node.

            If not given, it will default to any path set in the query, or the
            portal root. Note that in a navtree query, the root path will
            default to the portal only, possibly adjusted for any navtree_start
            set. If rootPath points to something not returned by the query by
            the query, a dummy node containing only an empty 'children' list
            will be returned.

            showAllParents -- a boolean property; if true and obj is given,
                ensure that all parents of the object, including any that would
                normally be filtered out are included in the tree.

            nodeFilter(node) -- a method returning a boolean; if this returns
                False, the given node will not be inserted in the tree

            subtreeFilter(node) -- a method returning a boolean; if this returns
                False, the given (folderish) node will not be expanded (its
                children will be pruned off)

            decoratorFactory(node) -- a method returning a dict; this can inject
                additional keys in a node being inserted.

    Returns tree where each node is represented by a dict:

        item            -   A catalog brain of this item
        depth           -   The depth of this item, relative to the startAt level
        currentItem     -   True if this is the current item
        currentParent   -   True if this is a direct parent of the current item
        children        -   A list of children nodes of this node

    Note: Any 'decoratorFactory' specified may modify this list, but
    the 'children' property is guaranteed to be there.

    Note: If the query does not return the root node itself, the root
    element of the tree may contain *only* the 'children' list.

    Note: Folder default-pages are not included in the returned result.
    If the 'obj' passed in is a default-page, its parent folder will be
    used for the purposes of selecting the 'currentItem'.
    """

    portal_url = getToolByName(context, 'portal_url')
    portal_catalog = getToolByName(context, 'portal_catalog')

    showAllParents = strategy.showAllParents
    rootPath = strategy.rootPath

    request = getattr(context, 'REQUEST', {})
    
    # Find the object's path. Use parent folder if context is a default-page

    objPath = None
    if obj is not None:
        if utils.isDefaultPage(obj, request):
            objPath = '/'.join(obj.getPhysicalPath()[:-1])
        else:
            objPath = '/'.join(obj.getPhysicalPath())

    portalPath = portal_url.getPortalPath()

    # Calculate rootPath from the path query if not set.

    if 'path' not in query:
        if rootPath is None:
            rootPath = portalPath
        query['path'] = rootPath
    elif rootPath is None:
        pathQuery = query['path']
        if type(pathQuery) == StringType:
            rootPath = pathQuery
        else:
            # Adjust for the fact that in a 'navtree' query, the actual path
            # is the path of the current context
            if pathQuery.get('navtree', False):
                navtreeLevel = pathQuery.get('navtree_start', 1)
                if navtreeLevel > 1:
                    navtreeContextPath = pathQuery['query']
                    navtreeContextPathElements = navtreeContextPath[len(portalPath)+1:].split('/')
                    # Short-circuit if we won't be able to find this path
                    if len(navtreeContextPathElements) < (navtreeLevel - 1):
                        return {'children' : []}
                    rootPath = portalPath + '/' + '/'.join(navtreeContextPathElements[:navtreeLevel-1])
                else:
                    rootPath = portalPath
            else:
                rootPath = pathQuery['query']

    rootDepth = len(rootPath.split('/'))

    # Default sorting and threatment of default-pages

    if 'sort_on' not in query:
        query['sort_on'] = 'getObjPositionInParent'

    if 'is_default_page' not in query:
        query['is_default_page'] = False

    results = portal_catalog.searchResults(query)

    # We keep track of a dict of item path -> node, so that we can easily
    # find parents and attach children. If a child appears before its
    # parent, we stub the parent node.

    # This is necessary because whilst the sort_on parameter will ensure
    # that the objects in a folder are returned in the right order relative
    # to each other, we don't know the relative order of objects from
    # different folders. So, if /foo comes before /bar, and /foo/a comes
    # before /foo/b, we may get a list like (/bar/x, /foo/a, /foo/b, /foo,
    # /bar,).

    itemPaths = {}

    def insertElement(itemPaths, item, forceInsert=False):
        """Insert the given 'item' brain into the tree, which is kept in
        'itemPaths'. If 'forceInsert' is True, ignore node- and subtree-
        filters, otherwise any node- or subtree-filter set will be allowed to
        block the insertion of a node.
        """
        itemPath = item.getPath()
        itemInserted = (itemPaths.get(itemPath, {}).get('item', None) is not None)

        # Short-circuit if we already added this item. Don't short-circuit
        # if we're forcing the insert, because we may have inserted but
        # later pruned off the node
        if not forceInsert and itemInserted:
            return

        itemPhysicalPath = itemPath.split('/')
        parentPath = '/'.join(itemPhysicalPath[:-1])
        parentPruned = (itemPaths.get(parentPath, {}).get('_pruneSubtree', False))

        # Short-circuit if we know we're pruning this item's parent

        # XXX: We could do this recursively, in case of parent of the
        # parent was being pruned, but this may not be a great trade-off

        # There is scope for more efficiency improvement here: If we knew we
        # were going to prune the subtree, we would short-circuit here each time.
        # In order to know that, we'd have to make sure we inserted each parent
        # before its children, by sorting the catalog result set (probably
        # manually) to get a breadth-first search.

        if not forceInsert and parentPruned:
            return

        isCurrent = isCurrentParent = False
        if objPath is not None:
            if objPath == itemPath:
                isCurrent = True
            elif objPath.startswith(itemPath):
                isCurrentParent = True

        relativeDepth = len(itemPhysicalPath) - rootDepth

        newNode = {'item'          : item,
                   'depth'         : relativeDepth,
                   'currentItem'   : isCurrent,
                   'currentParent' : isCurrentParent,}

        insert = True
        if not forceInsert and strategy is not None:
            insert = strategy.nodeFilter(newNode)
        if insert:

            if strategy is not None:
                newNode = strategy.decoratorFactory(newNode)

            # Tell parent about this item, unless an earlier subtree filter
            # told us not to. If we're forcing the insert, ignore the
            # pruning, but avoid inserting the node twice
            if itemPaths.has_key(parentPath):
                itemParent = itemPaths[parentPath]
                if forceInsert:
                    nodeAlreadyInserted = False
                    for i in itemParent['children']:
                        if i['item'].getPath() == itemPath:
                            nodeAlreadyInserted = True
                            break
                    if not nodeAlreadyInserted:
                        itemParent['children'].append(newNode)
                elif not itemParent.get('_pruneSubtree', False):
                    itemParent['children'].append(newNode)
            else:
                itemPaths[parentPath] = {'children': [newNode]}

            # Ask the subtree filter (if any), if we should be expanding this node
            if strategy.showAllParents and isCurrentParent:
                # If we will be expanding this later, we can't prune off children now
                expand = True
            else:
                expand = getattr(item, 'is_folderish', True)
            if expand and (not forceInsert and strategy is not None):
                expand = strategy.subtreeFilter(newNode)

            if expand:
                # If we had some orphaned children for this node, attach
                # them
                if itemPaths.has_key(itemPath):
                    newNode['children'] = itemPaths[itemPath]['children']
                else:
                    newNode['children'] = []
            else:
                newNode['children'] = []
                newNode['_pruneSubtree'] = True

            itemPaths[itemPath] = newNode

    # Add the results of running the query
    for r in results:
        insertElement(itemPaths, r)

    # If needed, inject additional nodes for the direct parents of the
    # context. Note that we use an unrestricted query: things we don't normally
    # have permission to see will be included in the tree.
    if strategy.showAllParents and objPath is not None:
        objSubPathElements = objPath[len(rootPath)+1:].split('/')
        parentPaths = []

        haveNode = (itemPaths.get(rootPath, {}).get('item', None) is None)
        if not haveNode:
            parentPaths.append(rootPath)

        parentPath = rootPath
        for i in range(len(objSubPathElements)):
            nodePath = rootPath + '/' + '/'.join(objSubPathElements[:i+1])
            node = itemPaths.get(nodePath, None)

            # If we don't have this node, we'll have to get it, if we have it
            # but it wasn't connected, re-connect it
            if node is None or 'item' not in node:
                parentPaths.append(nodePath)
            else:
                nodeParent = itemPaths.get(parentPath, None)
                if nodeParent is not None:
                    nodeAlreadyInserted = False
                    for i in nodeParent['children']:
                        if i['item'].getPath() == nodePath:
                            nodeAlreadyInserted = True
                            break
                    if not nodeAlreadyInserted:
                        nodeParent['children'].append(node)

            parentPath = nodePath

        # If we were outright missing some nodes, find them again
        if len(parentPaths) > 0:
            query = {'path' : {'query' : parentPaths, 'depth' : 0}}
            results = portal_catalog.unrestrictedSearchResults(query)

            for r in results:
                insertElement(itemPaths, r, forceInsert=True)

    # Return the tree starting at rootPath as the root node. If the
    # root path does not exist, we return a dummy parent node with no children.
    return itemPaths.get(rootPath, {'children' : []})


def getNavigationRoot(context):
    """Get the path to the root of the navigation tree. If context or one of
    its parents until (but not including) the portal root implements
    INavigationRoot, return this.

    Otherwise, if an explicit root is set in navtree_properties, use this. If
    the property is not set or is set to '/', use the portal root.
    """

    portal_url = getToolByName(context, 'portal_url')
    portal_properties = getToolByName(context, 'portal_properties')
    navtree_properties = getattr(portal_properties, 'navtree_properties')

    portal = portal_url.getPortalObject()
    obj = context
    while not INavigationRoot.providedBy(obj) and aq_base(obj) is not aq_base(portal):
        obj = utils.parent(obj)
    if INavigationRoot.providedBy(obj) and aq_base(obj) is not aq_base(portal):
        return '/'.join(obj.getPhysicalPath())

    rootPath = navtree_properties.getProperty('root', None)
    portalPath = portal_url.getPortalPath()
    contextPath = '/'.join(context.getPhysicalPath())

    if rootPath:
        if rootPath == '/':
            return portalPath
        else:
            if len(rootPath) > 1 and rootPath[0] == '/':
                return portalPath + rootPath
            else:
                return portalPath

    # This code is stolen from Sprout, but it's unclear exactly how it
    # should work and the test from Sprout isn't directly transferable
    # to testNavTree.py, since it's testing something slightly different.
    # Hoping Sidnei or someone else with a real use case can do this.
    # The idea is that if the 'root' variable is set to '', you'll get
    # the virtual root. This should probably also be used by the default
    # search, as well as the tabs and breadcrumbs. Also, the text in
    # prefs_navigation_form.cpt should be updated if this is re-enabled.
    #
    # Attempt to get use the virtual host root as root if an explicit
    # root is not set
    # if rootPath == '':
    #    request = getattr(context, 'REQUEST', None)
    #    if request is not None:
    #        vroot = request.get('VirtualRootPhysicalPath', None)
    #        if vroot is not None:
    #            return '/'.join(('',) + vroot[len(portalPath):])

    # Fall back on the portal root
    if not rootPath:
        return portalPath

# Strategy objects for the navtree creation code. You can subclass these
# to expand the default navtree behaviour, and pass instances of your subclasses
# to buildFolderTree().

class NavtreeQueryBuilder:
    """Build a navtree query based on the settings in navtree_properties
    """
    implements(INavigationQueryBuilder)

    def __init__(self, context):
        portal_properties = getToolByName(context, 'portal_properties')
        portal_url = getToolByName(context, 'portal_url')
        navtree_properties = getattr(portal_properties, 'navtree_properties')

        # Acquire a custom nav query if available
        customQuery = getattr(context, 'getCustomNavQuery', None)
        if customQuery is not None and utils.safe_callable(customQuery):
            query = customQuery()
        else:
            query = {}

        # Construct the path query

        rootPath = getNavigationRoot(context)
        currentPath = '/'.join(context.getPhysicalPath())

        # If we are above the navigation root, a navtree query would return
        # nothing (since we explicitly start from the root always). Hence,
        # use a regular depth-1 query in this case.

        if not currentPath.startswith(rootPath):
            query['path'] = {'query' : rootPath, 'depth' : 1}
        else:
            query['path'] = {'query' : currentPath, 'navtree' : 1}

        topLevel = navtree_properties.getProperty('topLevel', 0)
        if topLevel and topLevel > 0:
             query['path']['navtree_start'] = topLevel + 1

        # XXX: It'd make sense to use 'depth' for bottomLevel, but it doesn't
        # seem to work with EPI.

        # Only list the applicable types
        query['portal_type'] = utils.typesToList(context)

        # Apply the desired sort
        sortAttribute = navtree_properties.getProperty('sortAttribute', None)
        if sortAttribute is not None:
            query['sort_on'] = sortAttribute
            sortOrder = navtree_properties.getProperty('sortOrder', None)
            if sortOrder is not None:
                query['sort_order'] = sortOrder

        # Filter on workflow states, if enabled
        if navtree_properties.getProperty('enable_wf_state_filtering', False):
            query['review_state'] = navtree_properties.getProperty('wf_states_to_show', ())

        self.query = query

    def __call__(self):
        return self.query

class SitemapQueryBuilder(NavtreeQueryBuilder):
    """Build a folder tree query suitable for a sitemap
    """

    def __init__(self, context):
        NavtreeQueryBuilder.__init__(self, context)
        portal_url = getToolByName(context, 'portal_url')
        portal_properties = getToolByName(context, 'portal_properties')
        navtree_properties = getattr(portal_properties, 'navtree_properties')
        sitemapDepth = navtree_properties.getProperty('sitemapDepth', 2)
        self.query['path'] = {'query' : portal_url.getPortalPath(),
                              'depth' : sitemapDepth}

class SitemapNavtreeStrategy(NavtreeStrategyBase):
    """The navtree building strategy used by the sitemap, based on
    navtree_properties
    """
    implements(INavtreeStrategy)
    #adapts(*, ISiteMap)

    def __init__(self, context, view=None):
        self.context = [context]
        
        portal_url = getToolByName(context, 'portal_url')
        self.portal = portal_url.getPortalObject()
        portal_properties = getToolByName(context, 'portal_properties')
        navtree_properties = getattr(portal_properties, 'navtree_properties')
        site_properties = getattr(portal_properties, 'site_properties')
        self.excludedIds = {}
        for id in navtree_properties.getProperty('idsNotToList', ()):
            self.excludedIds[id] = True
        self.parentTypesNQ = navtree_properties.getProperty('parentMetaTypesNotToQuery', ())
        self.viewActionTypes = site_properties.getProperty('typesUseViewActionInListings', ())

        self.showAllParents = navtree_properties.getProperty('showAllParents', True)
        self.rootPath = getNavigationRoot(context)


    def nodeFilter(self, node):
        item = node['item']
        if getattr(item, 'getId', None) in self.excludedIds:
            return False
        elif getattr(item, 'exclude_from_nav', False):
            return False
        else:
            return True

    def subtreeFilter(self, node):
        portalType = getattr(node['item'], 'portal_type', None)
        if portalType is not None and portalType in self.parentTypesNQ:
            return False
        else:
            return True

    def decoratorFactory(self, node):
        context = utils.context(self)
        
        newNode = node.copy()
        item = node['item']

        portalType = getattr(item, 'portal_type', None)
        itemUrl = item.getURL()
        if portalType is not None and portalType in self.viewActionTypes:
            itemUrl += '/view'

        isFolderish = getattr(item, 'is_folderish', None)
        showChildren = False
        if isFolderish and (portalType is None or portalType not in self.parentTypesNQ):
            showChildren = True

        newNode['Title'] = utils.pretty_title_or_id(context, item)
        newNode['absolute_url'] = itemUrl
        newNode['getURL'] = itemUrl
        newNode['path'] = item.getPath()
        newNode['icon'] = getattr(item, 'getIcon', None)
        newNode['Creator'] = getattr(item, 'Creator', None)
        newNode['creation_date'] = getattr(item, 'CreationDate', None)
        newNode['portal_type'] = portalType
        newNode['review_state'] = getattr(item, 'review_state', None)
        newNode['Description'] = getattr(item, 'Description', None)
        newNode['getRemoteUrl'] = getattr(item, 'getRemoteUrl', None)
        newNode['show_children'] = showChildren
        newNode['no_display'] = False # We sort this out with the nodeFilter

        return newNode

class DefaultNavtreeStrategy(SitemapNavtreeStrategy):
    """The navtree strategy used for the default navigation portlet
    """
    implements(INavtreeStrategy)
    #adapts(*, INavigationTree)

    def __init__(self, context, view=None):
        SitemapNavtreeStrategy.__init__(self, context, view)
        portal_properties = getToolByName(context, 'portal_properties')
        navtree_properties = getattr(portal_properties, 'navtree_properties')
        # XXX: We can't do this with a 'depth' query to EPI...
        self.bottomLevel = navtree_properties.getProperty('bottomLevel', 0)
        if view is not None:
            self.rootPath = view.navigationTreeRootPath()
        else:
            self.rootPath = getNavigationRoot(context)

    def subtreeFilter(self, node):
        sitemapDecision = SitemapNavtreeStrategy.subtreeFilter(self, node)
        if sitemapDecision == False:
            return False
        depth = node.get('depth', 0)
        if depth > 0 and self.bottomLevel > 0 and depth >= self.bottomLevel:
            return False
        else:
            return True