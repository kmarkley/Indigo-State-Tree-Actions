#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################
# Copyright (c) 2014, Perceptive Automation, LLC. All rights reserved.
# http://www.indigodomo.com

import indigo
from itertools import groupby

# Note the "indigo" module is automatically imported and made available inside
# our global name space by the host process.

###############################################################################
# globals

kBaseChar       = u"|"
kStateChar      = u">"
kContextChar    = u"+"
kExitChar       = u"*"
kVarSepChar     = u"_"
kBaseReserved   = (kBaseChar,kStateChar,kContextChar,kExitChar,kVarSepChar)
kStateReserved  = (kBaseChar,kContextChar,kExitChar,kVarSepChar)
kChangedSuffix  = u"__LastChange"
kContextSuffix  = u"__Contexts"
kContextExtra   = u"__Context__"

################################################################################
class Plugin(indigo.PluginBase):

    #-------------------------------------------------------------------------------
    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)

    #-------------------------------------------------------------------------------
    def __del__(self):
        indigo.PluginBase.__del__(self)

    #-------------------------------------------------------------------------------
    # Start and Stop
    #-------------------------------------------------------------------------------
    def startup(self):
        self.debug = self.pluginPrefs.get("showDebugInfo",False)
        if self.debug:
            self.logger.debug("Debug logging enabled")
        self.debug = self.pluginPrefs.get("showDebugInfo",False)
        self.logMissing = self.pluginPrefs.get("logMissing", False)
        self.actionSleep = float(self.pluginPrefs.get("actionSleep",0))

        self.treeDict   = dict()
        namespaces      = self.pluginPrefs.get('namespaces',[])
        contextDict     = self.pluginPrefs.get('contextDict',{})
        lastStateDict   = self.pluginPrefs.get('lastStateDict',{})
        for namespace in namespaces:
            self.treeDict[namespace] = StateTree(self,
                namespace = namespace,
                lastState = lastStateDict.get(namespace,''),
                contexts  = list(contextDict.get(namespace,[]))
                )

    #-------------------------------------------------------------------------------
    def shutdown(self):
        self.savePluginPrefs()

    #-------------------------------------------------------------------------------
    def runConcurrentThread(self):
        try:
            while True:
                self.savePluginPrefs()
                self.sleep(600)
        except self.StopThread:
            pass

    #-------------------------------------------------------------------------------
    def savePluginPrefs(self):
        namespaces = list()
        contextDict = dict()
        lastStateDict = dict()
        for name, tree in self.treeDict.items():
            namespaces.append(name)
            contextDict[name] = tree.contexts
            lastStateDict[name] = tree.lastState

        flSave = False
        if self.pluginPrefs['namespaces'] != namespaces:
            self.pluginPrefs['namespaces'] = namespaces
            flSave = True
        if self.pluginPrefs['contextDict'] != contextDict:
            self.pluginPrefs['contextDict'] = contextDict
            flSave = True
        if self.pluginPrefs['lastStateDict'] != lastStateDict:
            self.pluginPrefs['lastStateDict'] = lastStateDict
            flSave = True
        if self.pluginPrefs['showDebugInfo'] != self.debug:
            self.pluginPrefs['showDebugInfo'] = self.debug
            flSave = True
        if self.pluginPrefs['logMissing'] != self.logMissing:
            self.pluginPrefs['logMissing'] = self.logMissing
            flSave = True
        if self.pluginPrefs['actionSleep'] != self.actionSleep:
            self.pluginPrefs['actionSleep'] = self.actionSleep
            flSave = True
        if flSave:
            indigo.server.savePluginPrefs()

    #-------------------------------------------------------------------------------
    # Config and Validate
    #-------------------------------------------------------------------------------
    def closedPrefsConfigUi(self, valuesDict, userCancelled):
        if not userCancelled:
            self.debug = valuesDict.get('showDebugInfo',False)
            if self.debug:
                self.logger.debug("Debug logging enabled")
            self.logMissing = valuesDict.get('logMissing',False)
            self.actionSleep = float(valuesDict.get('actionSleep',0))

    #-------------------------------------------------------------------------------
    def validatePrefsConfigUi(self, valuesDict):
        errorsDict = indigo.Dict()

        try:
            n = float(valuesDict.get('actionSleep'))
            if not ( 0.0 <= n <= 5.0 ):
                raise ValueError("actionSleep out of range")
        except:
            errorsDict['actionSleep'] = "Must be a number between 0.0 and 5.0"

        if len(errorsDict) > 0:
            return (False, valuesDict, errorsDict)
        return (True, valuesDict)

    #-------------------------------------------------------------------------------
    def validateActionConfigUi(self, valuesDict, typeId, devId, runtime=False):
        errorsDict = indigo.Dict()

        baseName = valuesDict.get('baseName',"")
        if baseName == "":
            errorsDict['baseName'] = "Base Name required"
        elif baseName not in self.treeDict:
            errorsDict['baseName'] = "Namespace '{}' does not exist".format(baseName)

        if typeId == 'enterNewState':
            stateName = valuesDict.get('stateName',"")
            if stateName == "":
                errorsDict['stateName'] = "State Name must be at least one character long"
            elif any(ch in stateName for ch in kStateReserved):
                errorsDict['stateName'] = "State Name may not contain:  "+"  ".join(kStateReserved)

        elif typeId in ('addContext','removeContext'):
            contextName = valuesDict.get('contextName',"")
            if contextName == "":
                errorsDict["contextName"] = "Context must be at least one character long"
            elif any(ch in contextName for ch in kBaseReserved):
                errorsDict['contextName'] = "Context may not contain:  "+"  ".join(kBaseReserved)

        elif typeId == 'variableToState':
            varId = valuesDict.get('stateVarId',"")
            if varId == "":
                errorsDict['stateVarId'] = "No variable defined"
            elif runtime:
                var = indigo.variables[int(varId)]
                if var.value == "":
                    errorsDict['stateVarId'] = "State Name must be at least one character long"
                elif any(ch in var.value for ch in kStateReserved):
                    errorsDict['stateVarId'] = "State Name may not contain:  "+"  ".join(kStateReserved)

        if len(errorsDict) > 0:
            return (False, valuesDict, errorsDict)
        return (True, valuesDict)

    #-------------------------------------------------------------------------------
    def _validateRuntime(self, action, typeId):
        valid = self.validateActionConfigUi(action.props, typeId, action.deviceId, runtime=True)
        if not valid[0]:
            self.logger.error('Action "{}" failed validation'.format(typeId))
            for key in valid[2]:
                self.logger.error('{}: {}'.format(key, valid[2][key]))
        return valid[0]

    #-------------------------------------------------------------------------------
    # Action Methods
    #-------------------------------------------------------------------------------
    def enterNewState(self, action):
        if self._validateRuntime(action, 'enterNewState'):
            self.treeDict[action.props['baseName']].stateChange(action.props['stateName'])

    #-------------------------------------------------------------------------------
    def variableToState (self, action):
        if self._validateRuntime(action, 'variableToState'):
            self.treeDict[action.props['baseName']].stateChange(indigo.variables[int(action.props['stateVarId'])].value)

    #-------------------------------------------------------------------------------
    def addContext(self, action):
        if self._validateRuntime(action, 'addContext'):
            self.treeDict[action.props['baseName']].contextChange(action.props['contextName'], True)


    #-------------------------------------------------------------------------------
    def removeContext(self, action):
        if self._validateRuntime(action, 'removeContext'):
            self.treeDict[action.props['baseName']].contextChange(action.props['contextName'], False)

    #-------------------------------------------------------------------------------
    # Menu Methods
    #-------------------------------------------------------------------------------
    def changeNamespace(self, valuesDict="", typeId=""):
        errorText = ""
        baseName = valuesDict.get('baseName',"")
        if typeId == 'addNamespace':
            if baseName in self.treeDict:
                errorText = "Base Name already exists"
            elif baseName == "":
                errorText = "Required"
            elif any(ch in baseName for ch in kBaseReserved):
                errorText = "Base Name may not contain:  "+"  ".join(kBaseReserved)
        elif typeId == 'removeNamespace':
            if baseName == "":
                errorText = "Required"
            elif baseName not in self.treeDict:
                errorText = "Base Name does not exist"
        if errorText:
            return (False, valuesDict, indigo.Dict({'baseName':errorText}))
        else:
            if typeId == 'addNamespace':
                self.treeDict[baseName] = StateTree(self, baseName)
                self.logger.info('>> namespace "{}" added'.format(baseName))
            elif typeId == 'removeNamespace':
                del self.treeDict[baseName]
                self.logger.info('>> namespace "{}" removed'.format(baseName))
            self.savePluginPrefs()
            return (True, valuesDict)

    #-------------------------------------------------------------------------------
    def toggleDebug(self):
        if self.debug:
            self.logger.debug("Debug logging disabled")
            self.debug = False
        else:
            self.debug = True
            self.logger.debug("Debug logging enabled")

    #-------------------------------------------------------------------------------
    def toggleLogMissing(self):
        self.logMissing = not self.logMissing
        self.logger.info("Log missing action groups {}".format(['disabled','enabled'][self.logMissing]))

    #-------------------------------------------------------------------------------
    # Menu Callbacks
    #-------------------------------------------------------------------------------
    def listNamespaces(self, filter="", valuesDict=None, typeId="", targetId=0):
        listArray = []
        for baseName in self.treeDict:
            listArray.append((baseName,baseName))
        return listArray

################################################################################
# Classes
################################################################################
class StateTree(object):

    #-------------------------------------------------------------------------------
    def __init__(self, plugin, namespace, lastState=None, contexts=list()):
        self.plugin     = plugin
        self.logger     = plugin.logger

        self.name       = namespace
        self.action     = namespace
        self.lastState  = lastState
        self.contexts   = contexts
        self.folder     = self._getFolder()
        self.lastVar    = self._getVar(self.name)
        self.changedVar = self._getVar(self.name+kChangedSuffix, strip=False)
        self.contextVar = self._getVar(self.name+kContextSuffix, strip=False)

        self.branch     = StateBranch(self, lastState)

    #-------------------------------------------------------------------------------
    def stateChange(self, newState):
        if newState != self.lastState:
            self.logger.info('>> go to state "{}"'.format(self.name+kBaseChar+newState))

            # execute global enter action group
            self.doAction(True)

            # back out old branch until it matches new branch
            oldBranch  = self.branch
            newBranch  = StateBranch(self, newState)
            leafnames = list(leaf.name for leaf in newBranch.leaves)
            for i, leaf in reversed(list(enumerate(oldBranch.leaves))):
                if leaf.name in leafnames:
                    i += 1
                    break
                leaf.doAction(False)
            else: i = 0   # if oldBranch is empty, i won't initialize

            # enter new branch from matching point
            for leaf in newBranch.leaves[i:]:
                leaf.doAction(True)

            # save new state and timestamp to variables
            self._setVar(self.lastVar, newState)
            self._setVar(self.changedVar, indigo.server.getTime())

            # execute global exit action group
            self.doAction(False)

            # save changes
            self.branch = newBranch
            self.lastState = newState

    #-------------------------------------------------------------------------------
    def contextChange(self, context, add):
        if [(context in self.contexts),(context not in self.contexts)][add]:
            self.logger.info('>> {} context "{}"'.format(['remove','add'][add], self.name+kContextChar+context))

            # execute global add context action group
            if add:
                self.doContext(context, True)
                self.contexts.append(context)

            # execute context action group for each nested state
            incr = [-1,1][add]
            for leaf in self.branch.leaves[::incr]:
                leaf.doContext(context, add)

            # execute global remove context action group
            if not add:
                self.doContext(context, False)
                self.contexts.remove(context)

            # save changes
            var = self._getVar(self.name + kContextExtra + context, False)
            self._setVar(var, add)
            self._setVar(self.contextVar, self.contexts)
            self._setVar(self.changedVar, indigo.server.getTime())

    #-------------------------------------------------------------------------------
    def doAction(self, enter):
        self._execute(self.action+[kExitChar,''][enter])

    #-------------------------------------------------------------------------------
    def doContext(self, context, add):
        self._execute(self.action+kContextChar+context+[kExitChar,''][add])

    #-------------------------------------------------------------------------------
    def _execute(self, action):
        try:
            indigo.actionGroup.execute(action)
            self.sleep(self.plugin.actionSleep)
        except:
            if self.plugin.logMissing:
                self.logger.info(action+" (missing)")

    #-------------------------------------------------------------------------------
    def _getFolder(self):
        if self.name not in indigo.variables.folders:
            folder = indigo.variables.folder.create(self.name)
        else:
            folder = indigo.variables.folders[self.name]
        return folder.id

    #-------------------------------------------------------------------------------
    def _setVar(self, var, value):
        # just tired of typing unicode()
        indigo.variable.updateValue(var.id, unicode(value))

    #-------------------------------------------------------------------------------
    def _getVar(self, name, strip=True):
        def trans(c):
            if c.isalnum():
                return c
            return kVarSepChar

        fixedName = ''.join(map(trans, name.strip()))
        if strip:
          fixedName =  ''.join(kVarSepChar if a==kVarSepChar else ''.join(b) for a,b in groupby(fixedName))
        try:
            var = indigo.variable.create(fixedName, folder=self.folder)
        except ValueError, e:
            if e.message == "NameNotUniqueError":
                var = indigo.variables[fixedName]
            else:
                self.logger.error("Variable error: %s" % (str(e)))
        if var and (var.folderId != self.folder):
            indigo.variable.moveToFolder(var, value=self.folder)
        return var

################################################################################
class StateBranch(object):

    #-------------------------------------------------------------------------------
    def __init__(self, tree, state):
        leaves = list()
        if state:
            leafnames = state.split(kStateChar)
            leaf  = ""
            for name in leafnames:
                leaf += name
                leaves.append(StateLeaf(tree, leaf))
                leaf += kStateChar
        self.leaves = tuple(leaves)

################################################################################
class StateLeaf(object):

    #-------------------------------------------------------------------------------
    def __init__(self, tree, leaf):
        self.tree       = tree
        self.name       = leaf
        self.action     = tree.name+kBaseChar+leaf
        self.var        = tree._getVar(self.action)

    #-------------------------------------------------------------------------------
    def doAction(self, enter):
        if enter: self.tree._execute(self.action)
        for context in self.tree.contexts:
            self.doContext(context, enter)
        if not enter: self.tree._execute(self.action+kExitChar)
        self.tree._setVar(self.var, enter)

    #-------------------------------------------------------------------------------
    def doContext(self, context, add):
        self.tree._execute(self.action+kContextChar+context+[kExitChar,''][add])
