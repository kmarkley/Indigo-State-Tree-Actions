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
        self.logger.debug(u"startup called")
        if self.debug:
            self.logger.debug("Debug logging enabled")
        self.folderId = self._getFolderId(self.pluginPrefs.get("folderName",None))
        self.logMissing = self.pluginPrefs.get("logMissing", False)
        self.debug = self.pluginPrefs.get("showDebugInfo",False)

    def shutdown(self):
        self.logger.debug(u"shutdown called")

    def closedPrefsConfigUi(self, valuesDict, userCancelled):
        self.logger.debug(u"closedPrefsConfigUi called")
        if not userCancelled:
            self.debug = valuesDict.get("showDebugInfo",False)
            if self.debug:
                self.logger.debug("Debug logging enabled")
            self.logMissing = valuesDict.get("logMissing",False)
            self.folderId = self._getFolderId(valuesDict.get("folderName",None))

    def validatePrefsConfigUi(self, valuesDict):
        self.logger.debug(u'Validating Prefs called')
        errorsDict = indigo.Dict()
        
        if not all(x.isalnum() or x.isspace() for x in valuesDict["folderName"]):
            errorsDict["folderName"] = "Folder Name may only contain letters, numbers, and spaces"
        
        if len(errorsDict) > 0:
            return (False, valuesDict, errorsDict)
        return (True, valuesDict)
    
    def validateActionConfigUi(self, valuesDict, typeId, devId):
        self.logger.debug(u"Validating action config for type: " + typeId)
        errorsDict = indigo.Dict()
        
        if valuesDict["baseName"] == u'':
            errorsDict["baseName"] = "Base Name must be at least one character long"
        elif any(ch in valuesDict["baseName"] for ch in kBaseReserved):
            errorsDict["baseName"] = "Base Name may not contain:  "+"  ".join(kBaseReserved)
            
        if typeId == "enterNewState":
            if valuesDict["stateName"] == u'':
                errorsDict["stateName"] = "State Name must be at least one character long"
            elif any(ch in valuesDict["stateName"] for ch in kStateReserved):
                errorsDict["stateName"] = "State Name may not contain:  "+"  ".join(kStateReserved)
        elif typeId in ("addContext","removeContext"):
            if valuesDict["contextName"] == u'':
                errorsDict["contextName"] = "Context must be at least one character long"
            elif any(ch in valuesDict["contextName"] for ch in kBaseReserved):
                errorsDict["contextName"] = "Context may not contain:  "+"  ".join(kBaseReserved)
        
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
        baseObj  = self.baseState(self, baseName)
        if newState != baseObj.value:
            oldTree  = self.stateTree(self, baseObj, baseObj.value)
            newTree  = self.stateTree(self, baseObj, newState)
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
            # save new state to variable for next time
            self._setValue(baseObj.var, newState)
            self._setValue(baseObj.changedVar, indigo.server.getTime())
    
    def addContext(self, action):
        baseName = action.props.get("baseName")
        context  = action.props.get("contextName")
        self.logger.debug(u"addContext: "+baseName+u"+"+context)
        baseObj  = self.baseState(self, baseName)
        if not (context in baseObj.contexts):
            oldTree  = self.stateTree(self, baseObj, baseObj.value)
            self._execute(baseObj.enterAction+kContextChar+context)
            for item in oldTree.states:
                self._execute(item.enterAction+kContextChar+context)
            baseObj.contexts.append(context)
            self._setValue(baseObj.contextVar, baseObj.contexts)
    
    def removeContext(self, action):
        baseName = action.props.get("baseName")
        context  = action.props.get("contextName")
        self.logger.debug(u"removeContext: "+baseName+u"+"+context)
        baseObj  = self.baseState(self, baseName)
        if (context in baseObj.contexts):
            oldTree  = self.stateTree(self, baseObj, baseObj.value)
            for item in oldTree.states[::-1]:
                self._execute(item.enterAction+kContextChar+context+kExitChar)
            self._execute(baseObj.enterAction+kContextChar+context+kExitChar)
            baseObj.contexts.remove(context)
            self._setValue(baseObj.contextVar, baseObj.contexts)
        
    
    ########################################
    # Classes
    ########################################
    
    # defines the namespace for hierarchical state trees
    class baseState(object):
        def __init__(self, pluginObj, baseName):
            pluginObj.logger.debug(u"baseState: "+baseName)
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

    # a single state within the hierarchy
    class singleState(object):
        def __init__(self, pluginObj, baseObj, stateName):
            pluginObj.logger.debug(u"singleState: "+stateName)
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
                    self.logger.error("Variable error: %s" % (str(e)), isErr=True)
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
                folder = indigo.variables.folder.create(valuesDict.get("folderName"))
            else:
                folder = indigo.variables.folders[name]
            return folder.id
        else:
            return 0
