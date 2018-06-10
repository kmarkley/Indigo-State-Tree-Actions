#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################
# Copyright (c) 2014, Perceptive Automation, LLC. All rights reserved.
# http://www.indigodomo.com

import indigo
import threading
import time
from itertools import groupby
from ghpu import GitHubPluginUpdater

# Note the "indigo" module is automatically imported and made available inside
# our global name space by the host process.

###############################################################################
# globals

kBaseChar       = "|"
kStateChar      = ">"
kContextChar    = "+"
kExitChar       = "*"
kVarSepChar     = "_"
kBaseReserved   = (kBaseChar,kStateChar,kContextChar,kExitChar,kVarSepChar)
kStateReserved  = (kBaseChar,kContextChar,kExitChar,kVarSepChar)
kPriorSuffix    = "__PriorState"
kChangedSuffix  = "__LastChange"
kContextSuffix  = "__Contexts"
kContextExtra   = "__Context__"

kEnter   = True
kExit    = False

k_updateCheckHours = 24

################################################################################
class Plugin(indigo.PluginBase):

    #-------------------------------------------------------------------------------
    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
        self.updater = GitHubPluginUpdater(self)

    #-------------------------------------------------------------------------------
    def __del__(self):
        indigo.PluginBase.__del__(self)

    #-------------------------------------------------------------------------------
    # Start, Stop, Plugin Prefs
    #-------------------------------------------------------------------------------
    def startup(self):
        self.nextCheck   = self.pluginPrefs.get('nextUpdateCheck',0)
        self.logMissing  = self.pluginPrefs.get("logMissing", False)
        self.actionSleep = float(self.pluginPrefs.get("actionSleep",0))
        self.debug       = self.pluginPrefs.get("showDebugInfo",False)
        if self.debug:
            self.logger.debug(u'Debug logging enabled')
        self.debug = self.pluginPrefs.get("showDebugInfo",False)

        lastStateDict = self.pluginPrefs.get('lastStateDict',{})
        contextDict   = self.pluginPrefs.get('contextDict',{})
        self.treeDict = {namespace:StateTree(self,
                                             namespace = namespace,
                                             lastState = lastStateDict.get(namespace,u''),
                                             contexts  = list(contextDict.get(namespace,[]))
                                            ) for namespace in lastStateDict}

    #-------------------------------------------------------------------------------
    def shutdown(self):
        self.savePluginPrefs()

    #-------------------------------------------------------------------------------
    def runConcurrentThread(self):
        try:
            while True:
                if time.time() > self.nextCheck:
                    self.checkForUpdates()
                self.sleep(600)
        except self.StopThread:
            pass

    #-------------------------------------------------------------------------------
    def savePluginPrefs(self):
        self.pluginPrefs['showDebugInfo']   = self.debug
        self.pluginPrefs['logMissing']      = self.logMissing
        self.pluginPrefs['actionSleep']     = self.actionSleep
        self.pluginPrefs['nextUpdateCheck'] = self.nextCheck

        indigo.server.savePluginPrefs()

    #-------------------------------------------------------------------------------
    def saveNamespaceStates(self):
        self.pluginPrefs['lastStateDict'] = {name:tree.lastState for name,tree in self.treeDict.items()}
        self.pluginPrefs['contextDict']   = {name:tree.contexts  for name,tree in self.treeDict.items()}

        indigo.server.savePluginPrefs()

    #-------------------------------------------------------------------------------
    # Config and Validate
    #-------------------------------------------------------------------------------
    def closedPrefsConfigUi(self, valuesDict, userCancelled):
        if not userCancelled:
            self.debug = valuesDict.get('showDebugInfo',False)
            self.logMissing = valuesDict.get('logMissing',False)
            self.actionSleep = float(valuesDict.get('actionSleep',0))

            self.logger.debug(u'Debug logging {}'.format(['disabled','enabled'][self.debug]))

    #-------------------------------------------------------------------------------
    def validatePrefsConfigUi(self, valuesDict):
        errorsDict = indigo.Dict()

        try:
            n = float(valuesDict.get('actionSleep',0.5))
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

        baseName = valuesDict.get('baseName',u"")
        if baseName == "":
            errorsDict['baseName'] = "Base Name required"
        elif baseName not in self.treeDict:
            errorsDict['baseName'] = "Namespace '{}' does not exist".format(baseName)

        if typeId == 'enterNewState':
            stateName = valuesDict.get('stateName',u"")
            if stateName == "":
                errorsDict['stateName'] = "State Name must be at least one character long"
            elif any(ch in stateName for ch in kStateReserved):
                errorsDict['stateName'] = "State Name may not contain:  "+"  ".join(kStateReserved)
            valuesDict['description'] = u"Enter '{}' state '{}'".format(baseName,stateName)

        elif typeId in ('addContext','removeContext'):
            contextName = valuesDict.get('contextName',u"")
            if contextName == "":
                errorsDict['contextName'] = "Context must be at least one character long"
            elif any(ch in contextName for ch in kBaseReserved):
                errorsDict['contextName'] = "Context may not contain:  "+"  ".join(kBaseReserved)
            valuesDict['description'] = u"{} '{}' context '{}'".format([u"Add",u"Remove"][typeId=='removeContext'],baseName,contextName)

        elif typeId == 'revertToPriorState':
            var = self.treeDict[baseName].priorVar
            if runtime:
                if var.value == "":
                    errorsDict['stateVarId'] = "State Name must be at least one character long"
                elif any(ch in var.value for ch in kStateReserved):
                    errorsDict['stateVarId'] = "State Name may not contain:  "+"  ".join(kStateReserved)
            valuesDict['description'] = u"Revert '{}' to prior state".format(baseName)

        elif typeId == 'variableToState':
            varId = valuesDict.get('stateVarId',u"")
            if varId == "":
                errorsDict['stateVarId'] = "No variable defined"
            else:
                var = indigo.variables[int(varId)]
            if runtime:
                if var.value == "":
                    errorsDict['stateVarId'] = "State Name must be at least one character long"
                elif any(ch in var.value for ch in kStateReserved):
                    errorsDict['stateVarId'] = "State Name may not contain:  "+"  ".join(kStateReserved)
            valuesDict['description'] = u"Enter '{}' state from variable '{}'".format(baseName,var.name)

        if len(errorsDict) > 0:
            return (False, valuesDict, errorsDict)
        return (True, valuesDict)

    #-------------------------------------------------------------------------------
    def _validateRuntime(self, action, typeId):
        valid = self.validateActionConfigUi(action.props, typeId, action.deviceId, runtime=True)
        if not valid[0]:
            self.logger.error(u'Action "{}" failed validation'.format(typeId))
            for key in valid[2]:
                self.logger.error(u'{}: {}'.format(key, valid[2][key]))
        return valid[0]

    #-------------------------------------------------------------------------------
    # Action Methods
    #-------------------------------------------------------------------------------
    def doStateTreeAction(self, action):
        if self._validateRuntime(action, action.pluginTypeId):
            tree = self.treeDict[action.props['baseName']]
            if action.pluginTypeId == 'enterNewState':
                tree.stateChange(action.props['stateName'])
            elif action.pluginTypeId == 'variableToState':
                tree.stateChange(indigo.variables[int(action.props['stateVarId'])].value)
            elif action.pluginTypeId == 'revertToPriorState':
                tree.stateChange(indigo.variables[tree.priorVar].value)
            elif action.pluginTypeId == 'addContext':
                tree.contextChange(action.props['contextName'], True)
            elif action.pluginTypeId == 'removeContext':
                tree.contextChange(action.props['contextName'], False)
            else:
                self.logger.error(u'Action not recognized: {}'.format(action.pluginTypeId))
            self.saveNamespaceStates()

    #-------------------------------------------------------------------------------
    # Menu Methods
    #-------------------------------------------------------------------------------
    def checkForUpdates(self):
        try:
            self.updater.checkForUpdate()
        except Exception as e:
            msg = 'Check for update error.  Next attempt in {} hours.'.format(k_updateCheckHours)
            if self.debug:
                self.logger.exception(msg)
            else:
                self.logger.error(msg)
                self.logger.debug(e)
        self.nextCheck = time.time() + k_updateCheckHours*60*60
        self.savePluginPrefs()

    #-------------------------------------------------------------------------------
    def updatePlugin(self):
        self.updater.update()

    #-------------------------------------------------------------------------------
    def forceUpdate(self):
        self.updater.update(currentVersion='0.0.0')

    #-------------------------------------------------------------------------------
    def changeNamespace(self, valuesDict="", typeId=""):
        errorText = ""
        baseName = valuesDict.get('baseName',u"")
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
                self.saveNamespaceStates()
                self.logger.info(u'>>> namespace "{}" added'.format(baseName))
            elif typeId == 'removeNamespace':
                del self.treeDict[baseName]
                self.saveNamespaceStates()
                self.logger.info(u'>>> namespace "{}" removed'.format(baseName))
            return (True, valuesDict)

    #-------------------------------------------------------------------------------
    def syncVariables(self, valuesDict="", typeId=""):
        if valuesDict.get('baseName',u""):
            self.treeDict[valuesDict['baseName']].syncVariables()
        return (True, valuesDict)

    #-------------------------------------------------------------------------------
    def toggleDebug(self):
        if self.debug:
            self.logger.debug(u'Debug logging disabled')
            self.debug = False
        else:
            self.debug = True
            self.logger.debug(u'Debug logging enabled')
        self.savePluginPrefs()

    #-------------------------------------------------------------------------------
    def toggleLogMissing(self):
        self.logMissing = not self.logMissing
        self.logger.info(u'Log missing action groups {}'.format(['disabled','enabled'][self.logMissing]))
        self.savePluginPrefs()

    #-------------------------------------------------------------------------------
    # Menu Callbacks
    #-------------------------------------------------------------------------------
    def listNamespaces(self, filter="", valuesDict=None, typeId="", targetId=0):
        return [(namespace,namespace) for namespace in self.treeDict]

################################################################################
# Classes
################################################################################
class StateTree(object):

    #-------------------------------------------------------------------------------
    def __init__(self, plugin, namespace, lastState=u"", contexts=list()):
        self.plugin     = plugin
        self.logger     = plugin.logger
        self.sleep      = plugin.sleep

        self.lock       = threading.Lock()

        self.name       = namespace
        self.actionName = namespace
        self.lastState  = lastState
        self.contexts   = contexts
        self.folder     = self._getFolder()
        self.lastVar    = self._getVar(self.name)
        self.priorVar   = self._getVar(self.name+kPriorSuffix,   double_underscores=True)
        self.changedVar = self._getVar(self.name+kChangedSuffix, double_underscores=True)
        self.contextVar = self._getVar(self.name+kContextSuffix, double_underscores=True)

        self.branch     = StateBranch(self, lastState)
        self.actionList = list()
        self.variableDict = dict()

    #-------------------------------------------------------------------------------
    def stateChange(self, newState):
        with self.lock:

            if not newState:
                self.logger.error(u'>>> no state defined "{}"'.format(self.name+kBaseChar+newState))
            if newState == self.lastState:
                self.logger.debug(u'>>> already in state "{}"'.format(self.name+kBaseChar+newState))
            else:
                self.logger.info(u'>>> go to state "{}"'.format(self.name+kBaseChar+newState))
                self.logger.debug(u'>>> prior state "{}"'.format(self.name+kBaseChar+self.lastState))

                # global enter action group
                self._setAction(kEnter)

                oldBranch  = self.branch
                newBranch  = StateBranch(self, newState)

                # back out old branch until it matches new branch
                leafnames = list(leaf.name for leaf in newBranch.leaves)
                for i, leaf in reversed(list(enumerate(oldBranch.leaves))):
                    if leaf.name in leafnames:
                        i += 1
                        break
                    leaf._setAction(kExit)
                else: i = 0   # if oldBranch is empty, i won't initialize

                # enter new branch from matching point
                for leaf in newBranch.leaves[i:]:
                    leaf._setAction(kEnter)

                # save new state and timestamp to variables
                self._queueVariable(self.priorVar, self.lastState)
                self._queueVariable(self.lastVar,  newState)
                self._queueVariable(self.changedVar, indigo.server.getTime())

                # global exit action group
                self._setAction(kExit)

                # save new state
                self.branch = newBranch
                self.lastState = newState

                # make the change
                self._executeActions()
                self._changeVariables()

    #-------------------------------------------------------------------------------
    def contextChange(self, context, enterExitBool):
        with self.lock:

            if [(context in self.contexts),(context not in self.contexts)][enterExitBool]:
                self.logger.info(u'>>> {} context "{}"'.format(['remove','add'][enterExitBool], self.name+kContextChar+context))

                # execute global add context action group
                if enterExitBool == kEnter:
                    self._setContext(context, kEnter)
                    self.contexts.append(context)

                # execute context action group for each nested state
                incr = [-1,1][enterExitBool]
                for leaf in self.branch.leaves[::incr]:
                    leaf._setContext(context, enterExitBool)

                # execute global remove context action group
                if enterExitBool == kExit:
                    self._setContext(context, kExit)
                    self.contexts.remove(context)

                # save changes
                self._queueVariable(self._getVar(self.name + kContextExtra + context, double_underscores=True), enterExitBool)
                self._queueVariable(self.contextVar, self._contextListString)
                self._queueVariable(self.changedVar, indigo.server.getTime())

                self._executeActions()
                self._changeVariables()

            else:
                self.logger.debug(u'>>> context "{}" already {}'.format(self.name+kContextChar+context, ['removed','added'][enterExitBool]))

    #-------------------------------------------------------------------------------
    def syncVariables(self):
        with self.lock:
            self.logger.debug(u'syncing variables for namespace "{}"'.format(self.name))

            # all variables in namespace folder default to False
            for var in indigo.variables.iter():
                if var.folderId == self.folder:
                    if var.id not in (self.lastVar.id, self.changedVar.id, self.contextVar.id):
                        self._queueVariable(var, False)
            # current leaves in state tree
            for leaf in self.branch.leaves:
                self._queueVariable(leaf.var, True)
            #current contexts
            for context in self.contexts:
                var = self._getVar(self.name + kContextExtra + context, double_underscores=True)
                self._queueVariable(var, True)
            # context list
            self._queueVariable(self.contextVar, self._contextListString)
            # last leaf
            self._queueVariable(self.lastVar, self.branch.leaves[-1].name)

            # update the variables
            self._changeVariables()

    #-------------------------------------------------------------------------------
    def _setAction(self, enterExitBool):
        self._queueAction(self.actionName+[kExitChar,''][enterExitBool])

    #-------------------------------------------------------------------------------
    def _setContext(self, context, enterExitBool):
        self._queueAction(self.actionName+kContextChar+context+[kExitChar,''][enterExitBool])

    #-------------------------------------------------------------------------------
    def _queueAction(self, action):
        self.actionList.append(action)

    #-------------------------------------------------------------------------------
    def _executeActions(self):
        self.logger.debug(u'>>> action groups:')
        for action in self.actionList:
            try:
                indigo.actionGroup.execute(action)
                self.logger.debug(u'    {}: executed'.format(action))
                self.sleep(self.plugin.actionSleep)
            except Exception as e:
                if isinstance(e, ValueError) and e.message.startswith('ElementNotFoundError'):
                    if self.plugin.logMissing:
                        self.logger.info(u'{}: missing'.format(action))
                    else:
                        self.logger.debug(u'    {}: missing'.format(action))
                else:
                    self.logger.error(u'{}: action group execute error \n{}'.format(self.name, e))
        self.actionList = list()

    #-------------------------------------------------------------------------------
    def _queueVariable(self, var, value):
        self.variableDict[var.id] = (var, value)

    #-------------------------------------------------------------------------------
    def _changeVariables(self):
        self.logger.debug(u'>>> variables:')
        for varId in self.variableDict:
            var, value = self.variableDict[varId]
            indigo.variable.updateValue(var.id, unicode(value))
            self.logger.debug(u'    {}: {}'.format(var.name,value))
        self.variableDict = dict()

    #-------------------------------------------------------------------------------
    def _getVar(self, name, double_underscores=False):
        fixedName = ''.join(x if x.isalnum() else kVarSepChar for x in name.strip())
        if not double_underscores:
            fixedName =  ''.join(kVarSepChar if a==kVarSepChar else ''.join(b) for a,b in groupby(fixedName))
        try:
            var = indigo.variables[fixedName]
            if var.folderId != self.folder:
                indigo.variable.moveToFolder(var, value=self.folder)
        except KeyError:
            var = indigo.variable.create(fixedName, folder=self.folder)
        return var

    #-------------------------------------------------------------------------------
    def _getFolder(self):
        if self.name not in indigo.variables.folders:
            folder = indigo.variables.folder.create(self.name)
        else:
            folder = indigo.variables.folders[self.name]
        return folder.id

    #-------------------------------------------------------------------------------
    @property
    def _contextListString(self):
        return u"[" + u", ".join(u"u'{}'".format(context) for context in self.contexts) + u"]"

################################################################################
class StateBranch(object):

    #-------------------------------------------------------------------------------
    def __init__(self, tree, state):
        leaves = list()
        if state:
            names = state.split(kStateChar)
            leaf  = ""
            for name in names:
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
        self.actionName = tree.name+kBaseChar+leaf
        self.var        = tree._getVar(self.actionName)

    #-------------------------------------------------------------------------------
    def _setAction(self, enterExitBool):
        self.tree._queueVariable(self.var, enterExitBool)
        if enterExitBool == kEnter: self.tree._queueAction(self.actionName)
        for context in self.tree.contexts:
            self._setContext(context, enterExitBool)
        if enterExitBool == kExit: self.tree._queueAction(self.actionName+kExitChar)

    #-------------------------------------------------------------------------------
    def _setContext(self, context, enterExitBool):
        self.tree._queueAction(self.actionName+kContextChar+context+[kExitChar,''][enterExitBool])
