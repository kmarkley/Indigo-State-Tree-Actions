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
    ########################################
    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
    
    def __del__(self):
        indigo.PluginBase.__del__(self)

    def startup(self):
        self.debug = self.pluginPrefs.get("showDebugInfo",False)
        self.logger.debug(u"startup")
        if self.debug:
            self.logger.debug("Debug logging enabled")
        self.folderId = self._getFolderId(self.pluginPrefs.get("folderName",None))
        self.logMissing = self.pluginPrefs.get("logMissing", False)
        self.debug = self.pluginPrefs.get("showDebugInfo",False)
        self.namespaces = self.pluginPrefs.get("namespaces",[])
        self.actionSleep = float(self.pluginPrefs.get("actionSleep",0))

    def shutdown(self):
        self.logger.debug(u"shutdown")
    
    
    ########################################
    # Config and Validate
    ########################################

    def closedPrefsConfigUi(self, valuesDict, userCancelled):
        self.logger.debug(u"closedPrefsConfigUi")
        if not userCancelled:
            self.debug = valuesDict.get("showDebugInfo",False)
            if self.debug:
                self.logger.debug("Debug logging enabled")
            self.logMissing = valuesDict.get("logMissing",False)
            self.folderId = self._getFolderId(valuesDict.get("folderName",None))
            self.actionSleep = float(valuesDict.get("actionSleep",0))

    def validatePrefsConfigUi(self, valuesDict):
        self.logger.debug(u"validatePrefsConfigUi")
        errorsDict = indigo.Dict()
        
        if not all(x.isalnum() or x.isspace() for x in valuesDict.get("folderName")):
            errorsDict["folderName"] = "Folder Name may only contain letters, numbers, and spaces"
        
        try:
            n = float(valuesDict.get("actionSleep"))
            if not ( 0.0 <= n <= 5.0 ):
                raise ValueError('actionSleep out of range')
        except:
            errorsDict["actionSleep"] = "Must be a number between 0.0 and 5.0"
        
        if len(errorsDict) > 0:
            return (False, valuesDict, errorsDict)
        return (True, valuesDict)
    
    def validateActionConfigUi(self, valuesDict, typeId, devId, runtime=False):
        self.logger.debug(u"validateActionConfigUi: " + typeId)
        errorsDict = indigo.Dict()
        
        if valuesDict.get("baseName",u'') == u'':
            errorsDict["baseName"] = u"Base Name must be at least one character long"
        elif any(ch in valuesDict.get("baseName",u'') for ch in kBaseReserved):
            errorsDict["baseName"] = u"Base Name may not contain:  "+"  ".join(kBaseReserved)
        elif runtime and valuesDict.get("baseName",u'') not in self.namespaces:
            errorsDict["baseName"] = u"Namespace '%s' does not exist" % valuesDict.get("baseName")
            
        if typeId == "enterNewState":
            if valuesDict.get("stateName",u'') == u'':
                errorsDict["stateName"] = u"State Name must be at least one character long"
            elif any(ch in valuesDict.get("stateName",u'') for ch in kStateReserved):
                errorsDict["stateName"] = u"State Name may not contain:  "+"  ".join(kStateReserved)
        
        elif typeId in ("addContext","removeContext"):
            if valuesDict.get("contextName",u'') == u'':
                errorsDict["contextName"] = u"Context must be at least one character long"
            elif any(ch in valuesDict.get("contextName",u'') for ch in kBaseReserved):
                errorsDict["contextName"] = u"Context may not contain:  "+"  ".join(kBaseReserved)
        
        elif typeId == "variableToState":
            if valuesDict.get("stateVarId",u'') == u'':
                self.logger.error("No variable defined")
                errorsDict["stateVarId"] = u"No variable defined"
            elif runtime:
                var = indigo.variables[int(valuesDict.get("stateVarId",u''))]
                if var.value == u'':
                    errorsDict["stateVarId"] = u"State Name must be at least one character long"
                elif any(ch in var.value for ch in kStateReserved):
                    errorsDict["stateVarId"] = u"State Name may not contain:  "+"  ".join(kStateReserved)
        
        if len(errorsDict) > 0:
            return (False, valuesDict, errorsDict)
        return (True, valuesDict)

    def _validateRuntime(self, action, typeId):
        valid = self.validateActionConfigUi(action.props, typeId, action.deviceId, runtime=True)
        if not valid[0]:
            self.logger.error(u"Action '%s' failed validation"%typeId)
            for key in valid[2]:
                self.logger.error(unicode(valid[2][key]))
        return valid[0]
    
    
    ########################################
    # Menu Methods
    ########################################
    
    def changeNamespace(self, valuesDict="", typeId=""):
        self.logger.debug(u"changeNamespace: " + typeId)
        errorsDict = indigo.Dict()
        baseName = valuesDict.get("baseName")
        if valuesDict.get("baseName","") == u'':
            errorsDict["baseName"] = "Base Name must be at least one character long"
        elif any(ch in valuesDict.get("baseName") for ch in kBaseReserved):
            errorsDict["baseName"] = "Base Name may not contain:  "+"  ".join(kBaseReserved)
        if typeId == "addNamespace":
            if not baseName in self.namespaces:
                self.namespaces.append(baseName)
            else:
                errorsDict["baseName"] = "Base Name already exists"
        elif typeId == "removeNamespace":
            if  baseName in self.namespaces:
                self.namespaces.remove(baseName)
            else:
                errorsDict["baseName"] = "Base Name does not exist"
        self.pluginPrefs["namespaces"] = self.namespaces
        if len(errorsDict) > 0:
            return (False, valuesDict, errorsDict)
        return (True, valuesDict)
    
    def listNamespaces(self, filter="", valuesDict=None, typeId="", targetId=0):
        listArray = []
        for baseName in self.namespaces:
            listArray.append((baseName,baseName))
        return listArray
    
    
    ########################################
    # Action Methods
    ########################################
    
    def enterNewState(self, action):
        self.logger.debug(u"enterNewState")
        if self._validateRuntime(action, "enterNewState"):
            self._doStateChange(action)
        
    def variableToState (self, action):
        self.logger.debug(u"variableToState: "+indigo.variables[int(action.stateVarId)].name)
        if self._validateRuntime(action, "variableToState"):
            action.props["stateName"] = indigo.variables[int(action.stateVarId)].value
            self._doStateChange(action)
    
    def _doStateChange(self, action):
        baseName = action.props.get("baseName")
        newState = action.props.get("stateName")
        baseObj  = self.baseState(self, baseName)
        self.logger.debug(u"_doStateChange: "+baseName+kBaseChar+newState)
        if newState != baseObj.value:
            oldTree  = self.stateTree(self, baseObj, baseObj.value)
            newTree  = self.stateTree(self, baseObj, newState)
            # execute global enter action group
            baseObj.stateAction(True)
            # back out old tree until it matches new tree
            matchList = list(item.name for item in newTree.states)
            for i, item in reversed(list(enumerate(oldTree.states))):
                if item.name in matchList:
                    i += 1
                    break
                item.stateAction(False)
            else: i = 0   # if oldTree is empty, i won't initialize
            # enter new tree from matching point
            for item in newTree.states[i:]:
                item.stateAction(True)
            # save new state and timestamp to variables
            self._setVar(baseObj.var, newState)
            self._setVar(baseObj.changedVar, indigo.server.getTime())
            # execute global exit action group
            baseObj.stateAction(False)
    
    def addContext(self, action):
        self.logger.debug(u"addContext")
        if self._validateRuntime(action, "addContext"):
            self._doContextChange(action, True)
    
    def removeContext(self, action):
        self.logger.debug(u"removeContext")
        if self._validateRuntime(action, "removeContext"):
            self._doContextChange(action, False)
        
    def _doContextChange(self, action, addFlag):
        baseName = action.props.get("baseName")
        context  = action.props.get("contextName")
        self.logger.debug(u"_doContextChange: "+baseName+kContextChar+context+[kExitChar,''][addFlag])
        baseObj  = self.baseState(self, baseName)
        if baseObj.updateContexts(context, addFlag):
            oldTree  = self.stateTree(self, baseObj, baseObj.value)
            # execute global add context action group
            if addFlag: baseObj.changeContext(context, True)
            # execute context action group for each nested state
            incr = [-1,1][addFlag]
            for item in oldTree.states[::incr]:
                item.changeContext(context, addFlag)
            # execute global remove context action group
            if not addFlag: baseObj.changeContext(context, False)
            baseObj.saveContext(context, addFlag)
        
   
    ########################################
    # Classes
    ########################################
    
    # defines the namespace for hierarchical state trees
    class baseState(object):
        def __init__(self, pluginObj, baseName):
            pluginObj.logger.debug(u"baseState: "+baseName)
            self.name           = baseName
            self.var            = pluginObj._getVar(self.name)
            self.value          = self.var.value
            self.changedVar     = pluginObj._getVar(self.name+kChangedSuffix, strip=False)
            self.contextVar     = pluginObj._getVar(self.name+kContextSuffix, strip=False)
            self.actionName     = self.name
            try:
                self.contexts = eval(self.contextVar.value)
            except:
                self.contexts = []
            self.pluginObj      = pluginObj
        
        def stateAction(self, enterFlag):
            self.pluginObj._execute(self.actionName+[kExitChar,''][enterFlag])
        
        def changeContext(self, context, addFlag):
            self.pluginObj._execute(self.actionName+kContextChar+context+[kExitChar,''][addFlag])
        
        def updateContexts(self, context, addFlag):
            if (addFlag) and (context not in self.contexts):
                self.contexts.append(context)
            elif (not addFlag) and (context in self.contexts):
                self.contexts.remove(context)
            else:
                return False
            self.pluginObj._setVar(self.contextVar, self.contexts)
            return True
        
        def saveContext(self, context, addFlag):
            var = self.pluginObj._getVar(self.actionName+kContextExtra+context, strip=False)
            self.pluginObj._setVar(var, addFlag)
        
        
    # a single state within the hierarchy
    class singleState(object):
        def __init__(self, pluginObj, baseObj, stateName):
            pluginObj.logger.debug(u"singleState: "+stateName)
            self.name           = stateName
            self.actionName     = baseObj.name+kBaseChar+stateName
            self.var            = pluginObj._getVar(self.actionName)
            self.pluginObj      = pluginObj
            self.baseObj        = baseObj
        
        def stateAction(self, enterFlag):
            if enterFlag: self.pluginObj._execute(self.actionName)
            for context in self.baseObj.contexts:
                self.changeContext(context, enterFlag)
            if not enterFlag: self.pluginObj._execute(self.actionName+kExitChar)
            self.pluginObj._setVar(self.var, enterFlag)
    
        def changeContext(self, context, addFlag):
            self.pluginObj._execute(self.actionName+kContextChar+context+[kExitChar,''][addFlag])


    # a full list of nested states
    class stateTree(object):
        def __init__(self, pluginObj, baseObj, stateName):
            pluginObj.logger.debug(u"stateTree: "+stateName)
            self.states = []
            if stateName != u'':
                branches    = stateName.split(kStateChar)
                trunk       = ""
                for branch in branches:
                    trunk += branch
                    oneState = Plugin.singleState(pluginObj, baseObj, trunk)
                    self.states.append(oneState)
                    trunk += kStateChar
        
    
    ########################################
    # Utilities
    ########################################

    
    # Action Groups
    def _execute(self, groupName):
        self.logger.debug(u"_execute: "+groupName)
        try:
            indigo.actionGroup.execute(groupName)
            self.sleep(self.actionSleep)
        except:
            if self.logMissing:
                self.logger.info(groupName+u" (missing)")

    # Variables
    def _setVar(self, var, value):
        # just tired of typing unicode()
        indigo.variable.updateValue(var.id, unicode(value))
    
    def _getVar(self, name, strip=True):
        def trans(c):
            if c.isalnum():
                return c
            return kVarSepChar
        
        fixedName = ''.join(map(trans, name.strip()))
        if strip:
          fixedName =  ''.join(kVarSepChar if a==kVarSepChar else ''.join(b) for a,b in groupby(fixedName))
        self.logger.debug(u"_getVar: "+fixedName)
        try:
            var = indigo.variable.create(fixedName, folder=self.folderId)
        except ValueError, e:
            if e.message == "NameNotUniqueError":
                var = indigo.variables[fixedName]
            else:
                self.logger.error("Variable error: %s" % (str(e)))
        if var and (var.folderId != self.folderId):
            indigo.variable.moveToFolder(var, value=self.folderId)
        return var
    
    def _getFolderId(self, name):
        self.logger.debug(u"_getFolderId: "+name)
        if name:
            if name not in indigo.variables.folders:
                folder = indigo.variables.folder.create(name)
            else:
                folder = indigo.variables.folders[name]
            return folder.id
        else:
            return 0
