#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################
# Copyright (c) 2014, Perceptive Automation, LLC. All rights reserved.
# http://www.indigodomo.com

import indigo
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
    # Start and Stop
    #-------------------------------------------------------------------------------
    def startup(self):
        self.nextCheck   = self.pluginPrefs.get('nextUpdateCheck',0)
        self.logMissing  = self.pluginPrefs.get("logMissing", False)
        self.actionSleep = float(self.pluginPrefs.get("actionSleep",0))
        self.debug       = self.pluginPrefs.get("showDebugInfo",False)
        if self.debug:
            self.logger.debug("Debug logging enabled")
        self.debug = self.pluginPrefs.get("showDebugInfo",False)

        self.treeDict    = dict()
        namespaces       = self.pluginPrefs.get('namespaces',[])
        contextDict      = self.pluginPrefs.get('contextDict',{})
        lastStateDict    = self.pluginPrefs.get('lastStateDict',{})
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
                if time.time() > self.nextCheck:
                    self.checkForUpdates()
                    self.nextCheck = time.time() + k_updateCheckHours*60*60
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
        if self.pluginPrefs.get('namespaces',[]) != namespaces:
            self.pluginPrefs['namespaces'] = namespaces
            flSave = True
        if self.pluginPrefs.get('contextDict',{}) != contextDict:
            self.pluginPrefs['contextDict'] = contextDict
            flSave = True
        if self.pluginPrefs.get('lastStateDict',{}) != lastStateDict:
            self.pluginPrefs['lastStateDict'] = lastStateDict
            flSave = True
        if self.pluginPrefs.get('showDebugInfo',False) != self.debug:
            self.pluginPrefs['showDebugInfo'] = self.debug
            flSave = True
        if self.pluginPrefs.get('logMissing',False) != self.logMissing:
            self.pluginPrefs['logMissing'] = self.logMissing
            flSave = True
        if self.pluginPrefs.get('actionSleep',0.5) != self.actionSleep:
            self.pluginPrefs['actionSleep'] = self.actionSleep
            flSave = True
        if self.pluginPrefs.get('nextUpdateCheck',0) != self.nextCheck:
            self.pluginPrefs['nextUpdateCheck'] = self.nextCheck
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
                errorsDict['contextName'] = "Context must be at least one character long"
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
    def checkForUpdates(self):
        self.updater.checkForUpdate()

    #-------------------------------------------------------------------------------
    def updatePlugin(self):
        self.updater.update()

    #-------------------------------------------------------------------------------
    def forceUpdate(self):
        self.updater.update(currentVersion='0.0.0')

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
        self.sleep      = plugin.sleep

        self.name       = namespace
        self.action     = namespace
        self.lastState  = lastState
        self.contexts   = contexts
        self.folder     = self._getFolder()
        self.lastVar    = self._getVar(self.name)
        self.changedVar = self._getVar(self.name+kChangedSuffix, double_underscores=True)
        self.contextVar = self._getVar(self.name+kContextSuffix, double_underscores=True)

        self.branch     = StateBranch(self, lastState)

    #-------------------------------------------------------------------------------
    def stateChange(self, newState):
        if newState != self.lastState:
            self.logger.info('>> go to state "{}"'.format(self.name+kBaseChar+newState))

            # execute global enter action group
            self.doAction(kEnter)

            # back out old branch until it matches new branch
            oldBranch  = self.branch
            newBranch  = StateBranch(self, newState)
            leafnames = list(leaf.name for leaf in newBranch.leaves)
            for i, leaf in reversed(list(enumerate(oldBranch.leaves))):
                if leaf.name in leafnames:
                    i += 1
                    break
                leaf.doAction(kExit)
            else: i = 0   # if oldBranch is empty, i won't initialize

            # enter new branch from matching point
            for leaf in newBranch.leaves[i:]:
                leaf.doAction(kEnter)

            # save new state and timestamp to variables
            self._setVar(self.lastVar, newState)
            self._setVar(self.changedVar, indigo.server.getTime())

            # execute global exit action group
            self.doAction(kExit)

            # save changes
            self.branch = newBranch
            self.lastState = newState

    #-------------------------------------------------------------------------------
    def contextChange(self, context, enterExitBool):
        if [(context in self.contexts),(context not in self.contexts)][enterExitBool]:
            self.logger.info('>> {} context "{}"'.format(['remove','add'][enterExitBool], self.name+kContextChar+context))

            # execute global add context action group
            if enterExitBool == kEnter:
                self.doContext(context, kEnter)
                self.contexts.append(context)

            # execute context action group for each nested state
            incr = [-1,1][enterExitBool]
            for leaf in self.branch.leaves[::incr]:
                leaf.doContext(context, enterExitBool)

            # execute global remove context action group
            if enterExitBool == kExit:
                self.doContext(context, kExit)
                self.contexts.remove(context)

            # save changes
            var = self._getVar(self.name + kContextExtra + context, double_underscores=True)
            self._setVar(var, enterExitBool)
            self._setVar(self.contextVar, self.contexts)
            self._setVar(self.changedVar, indigo.server.getTime())

    #-------------------------------------------------------------------------------
    def doAction(self, enterExitBool):
        self._execute(self.action+[kExitChar,''][enterExitBool])

    #-------------------------------------------------------------------------------
    def doContext(self, context, enterExitBool):
        self._execute(self.action+kContextChar+context+[kExitChar,''][enterExitBool])

    #-------------------------------------------------------------------------------
    def _execute(self, action):
        try:
            indigo.actionGroup.execute(action)
            self.sleep(self.plugin.actionSleep)
        except Exception as e:
            if isinstance(e, ValueError) and e.message.startswith('ElementNotFoundError'):
                if self.plugin.logMissing:
                    self.logger.info("{} (missing)".format(action))
            else:
                self.logger.error('{}: action group execute error \n{}'.format(self.name, e))

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
    def _getVar(self, name, double_underscores=False):
        fixedName = ''.join(x if x.isalnum() else kVarSepChar for x in name.strip())
        if not double_underscores:
          fixedName =  ''.join(kVarSepChar if a==kVarSepChar else ''.join(b) for a,b in groupby(fixedName))
        try:
            var = indigo.variable.create(fixedName, folder=self.folder)
        except Exception as e:
            if isinstance(e, ValueError) and e.message.startswith('NameNotUniqueError'):
                var = indigo.variables[fixedName]
            else:
                self.logger.error('{}: variable error \n{}'.format(self.name, e))
        if var and (var.folderId != self.folder):
            indigo.variable.moveToFolder(var, value=self.folder)
        return var

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
        self.action     = tree.name+kBaseChar+leaf
        self.var        = tree._getVar(self.action)

    #-------------------------------------------------------------------------------
    def doAction(self, enterExitBool):
        if enterExitBool == kEnter: self.tree._execute(self.action)
        for context in self.tree.contexts:
            self.doContext(context, enterExitBool)
        if enterExitBool == kExit: self.tree._execute(self.action+kExitChar)
        self.tree._setVar(self.var, enterExitBool)

    #-------------------------------------------------------------------------------
    def doContext(self, context, enterExitBool):
        self.tree._execute(self.action+kContextChar+context+[kExitChar,''][enterExitBool])
