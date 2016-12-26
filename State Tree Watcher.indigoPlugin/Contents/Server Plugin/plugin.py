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
kContextSuffix  = u"__Context"
kContextExtra   = u"__"

################################################################################
class Plugin(indigo.PluginBase):
    ########################################
    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
    
    def __del__(self):
        indigo.PluginBase.__del__(self)

    ########################################
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
            errorsDict["actionSleep"] = "Must be a number between 0 and 5"
        
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
        elif valuesDict.get("baseName",u'') not in self.namespaces:
            errorsDict["baseName"] = u"Base Name does not exist"
            
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

    ########################################
    # Action Methods
    ########################################
    
    def enterNewState(self, action):
        baseName = action.props.get("baseName")
        newState = action.props.get("stateName")
        self.logger.debug(u"enterNewState: "+baseName+u"|"+newState)
        valid = self.validateActionConfigUi(action.props, "newState", action.deviceId, runtime=True)
        if not valid[0]:
            self.logger.error(u"Action 'Variable To State' failed validation")
            for key in valid[2]:
                self.logger.error(unicode(valid[2][key]))
            return
        self._doStateChange(baseName, newState)
        
    def variableToState (self, action):
        baseName = action.props.get("baseName")
        stateVarId = action.props.get("stateVarId")
        self.logger.debug(u"variableToState: "+baseName+u" ["+stateVarId+u"]")
        valid = self.validateActionConfigUi(action.props, "variableToState", action.deviceId, runtime=True)
        if not valid[0]:
            self.logger.error(u"Action 'Variable To State' failed validation")
            for key in valid[2]:
                self.logger.error(unicode(valid[2][key]))
            return
        self._doStateChange(baseName, indigo.variables[int(stateVarId)].value)
    
    def addContext(self, action):
        baseName = action.props.get("baseName")
        context  = action.props.get("contextName")
        self.logger.debug(u"addContext: "+baseName+u"+"+context)
        valid = self.validateActionConfigUi(action.props, "addContext", action.deviceId, runtime=True)
        if not valid[0]:
            self.logger.error(u"Action 'Add Context' failed validation")
            for key in valid[2]:
                self.logger.error(unicode(valid[2][key]))
            return
        baseObj  = self.baseState(self, baseName)
        if not (context in baseObj.contexts):
            oldTree  = self.stateTree(self, baseObj, baseObj.value)
            # execute global context action group
            self._execute(baseObj.enterAction+kContextChar+context)
            # execute context action group for each nested state
            for item in oldTree.states:
                self._execute(item.enterAction+kContextChar+context)
            # save the new context list
            baseObj.addContext(context)
    
    def removeContext(self, action):
        baseName = action.props.get("baseName")
        context  = action.props.get("contextName")
        self.logger.debug(u"removeContext: "+baseName+u"+"+context)
        valid = self.validateActionConfigUi(action.props, "removeContext", action.deviceId, runtime=True)
        if not valid[0]:
            self.logger.error(u"Action 'Remove Context' failed validation")
            for key in valid[2]:
                self.logger.error(unicode(valid[2][key]))
            return
        baseObj  = self.baseState(self, baseName)
        if (context in baseObj.contexts):
            oldTree  = self.stateTree(self, baseObj, baseObj.value)
            # execute context action group for each nested state (reverse order)
            for item in oldTree.states[::-1]:
                self._execute(item.enterAction+kContextChar+context+kExitChar)
            # execute global context action group
            self._execute(baseObj.enterAction+kContextChar+context+kExitChar)
            # save the new context list
            baseObj.removeContext(context)
        
    
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
                errorsDict["baseName"] = "Base Name already exist"
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
    # Classes
    ########################################
    
    # defines the namespace for hierarchical state trees
    class baseState(object):
        def __init__(self, pluginObj, baseName):
            pluginObj.logger.debug(u"class 'baseState': "+baseName)
            self.name           = baseName
            self.var            = pluginObj._getVariable(self.name)
            self.value          = self.var.value
            self.changedVar     = pluginObj._getVariable(self.name + kChangedSuffix, strip=False)
            self.contextVar     = pluginObj._getVariable(self.name + kContextSuffix, strip=False)
            self.enterAction    = self.name
            self.exitAction     = self.name+kExitChar
            try:
                self.contexts = eval(self.contextVar.value)
            except:
                self.contexts = []
            self.pluginObj      = pluginObj
        
        def enter(self):
            self.pluginObj._execute(self.enterAction)
    
        def exit(self):
            self.pluginObj._execute(self.exitAction)
        
        def addContext(self, context):
            if not (context in self.contexts):
                self.contexts.append(context)
                self.pluginObj._setValue(self.contextVar, self.contexts)
                var = self.pluginObj._getVariable(self.contextVar.name+kContextExtra+context, strip=False)
                self.pluginObj._setValue(var, True)
        
        def removeContext(self, context):
            if (context in self.contexts):
                self.contexts.remove(context)
                self.pluginObj._setValue(self.contextVar, self.contexts)
                var = self.pluginObj._getVariable(self.contextVar.name+kContextExtra+context, strip=False)
                self.pluginObj._setValue(var, False)
        

    # a single state within the hierarchy
    class singleState(object):
        def __init__(self, pluginObj, baseObj, stateName):
            pluginObj.logger.debug(u"class 'singleState': "+stateName)
            self.name           = stateName
            self.var            = pluginObj._getVariable(baseObj.name+kBaseChar+stateName)
            self.enterAction    = baseObj.name+kBaseChar+stateName
            self.exitAction     = baseObj.name+kBaseChar+stateName+kExitChar
            self.pluginObj      = pluginObj
            self.baseObj        = baseObj
        
        def enter(self):
            self.pluginObj._setValue(self.var, True)
            self.pluginObj._execute(self.enterAction)
            if self.baseObj.contexts:
                for context in self.baseObj.contexts:
                    self.pluginObj._execute(self.enterAction+kContextChar+context)
    
        def exit(self):
            self.pluginObj._setValue(self.var, False)
            if self.baseObj.contexts:
                for context in self.baseObj.contexts:
                    self.pluginObj._execute(self.enterAction+kContextChar+context+kExitChar)
            self.pluginObj._execute(self.exitAction)


    # a full list of nested states
    class stateTree(object):
        def __init__(self, pluginObj, baseObj, stateName):
            pluginObj.logger.debug(u"class 'stateTree': "+stateName)
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

    
    def _doStateChange(self, baseName, newState):
        self.logger.debug(u"_doStateChange: "+baseName+u"|"+newState)
        baseObj  = self.baseState(self, baseName)
        if newState != baseObj.value:
            oldTree  = self.stateTree(self, baseObj, baseObj.value)
            newTree  = self.stateTree(self, baseObj, newState)
            # save new state and timestamp to variables
            self._setValue(baseObj.var, newState)
            self._setValue(baseObj.changedVar, indigo.server.getTime())
            # execute global enter action group
            baseObj.enter()
            # back out old tree until it matches new tree
            matchList = list(item.name for item in newTree.states)
            for i, item in reversed(list(enumerate(oldTree.states))):
                if item.name in matchList:
                    i += 1
                    break
                item.exit()
            else: i = 0   # if oldTree is empty, i won't initialize
            # enter new tree from matching point
            for item in newTree.states[i:]:
                item.enter()
            # execute global exit action group
            baseObj.exit()
    
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
    def _setValue(self, var, value):
        indigo.variable.updateValue(var.id, unicode(value))
    
    def _getVariable(self, name, force=True, strip=True):
        def trans(c):
            if c.isalnum():
                return c
            return kVarSepChar
        def varNameFix(name, strip=True):
            str = ''.join(map(trans, name.strip()))
            if strip:
              str =  ''.join(kVarSepChar if a==kVarSepChar else ''.join(b) for a,b in groupby(str))
            return str
        
        fixedName = unicode(varNameFix(name, strip))
        self.logger.debug(u"_getVariable: "+fixedName)
        if force:
            try:
                var = indigo.variable.create(fixedName, folder=self.folderId)
            except ValueError, e:
                if e.message == "NameNotUniqueError":
                    var = indigo.variables[fixedName]
                else:
                    self.logger.error("Variable error: %s" % (str(e)))
        else:
            try:
                var = indigo.variables[fixedName]
            except:
                var = None
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
