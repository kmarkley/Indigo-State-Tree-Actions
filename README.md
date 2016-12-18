# State Tree Watcher

*(inspired by the variable-watcher.py example script here: http://wiki.indigodomo.com/doku.php?id=advanced_thermo)*

## Overview

This plugin creates actions to automate execution of multiple Action Groups based on a hierarchical tree-like structure of '_states_'.  Additional Action Groups are executed for each state depending on multiple inherited '_contexts_'.  The system is analogous to hooks in software development.

Additionally the plugin creates and maintains multiple Variables that track each '_state_' for use in Schedule and/or Trigger conditinals.

## Details

#### State Changes

Imagine a simple set of nested/hierarchical states like this:

	HouseState
	   Home
	       Wake
	       Sleep
	   Away
	       Work
	       Vacation

Each state is mutually-exclusive (you can't be both asleep and awake).

Indigo's example variable-wather.py script would enable executing an Action Group associated with each state. However, when exiting a state one might reasonable want to un-do whatever actions were taken when entering.

When changing from one state to another, this plugin will traverse 'up' the hierarchy of states being exited, attempting to execute an Action Group at each step, then traverse 'down' the hierachy, attempting to execute more Action Groups for each state entered.

Additionally, the plugin will attempt to execute a global enter and global exit Action Group whenever there is any change in state.

In the example above, when switching from the 'Work' state to the 'Wake' state, the plugin will try to execute these Action Groups:

	Global Enter
	Exit Work
	Exit Away
	Enter Home
	Enter Wake
	Global Exit

#### Contexts

Additionally, the plugin modifies states with _contexts_.

Unlike states, contexts are not mutually-exclusive and are inherited by all states.

For example, you may be at work when it is dark, or at home when it is dark.  You may have guests when you are awake or asleep.

For every combination of states and contexts, both an enter Action Group and an exit Action Group may be executed.  

So again in the example above, when switching from the 'Work' state to the 'Wake' state when dark, the following Action Groups might be executed:

	Global Enter
	Exit Work/Dark
	Exit Work
	Exit Away/Dark
	Exit Away
	Enter Home
	Enter Home/Dark
	Enter Wake
	Enter Wake/Dark
	Global Exit

Importantly, ***any Action Group that does not exist will be silently skipped***.


## Naming Conventions

All this is accomplished using **strict naming conventions** for Action Groups.

Each state change must have a '_Base Name_' that defines the namespace for all Action Groups.  In the example above, this is 'HouseState'.  This is also the name of the global enter Action Group.

The pipe ('|') character is used to separate the Base Name from the rest of the Action Group name.

Hierarchichal states ate listed in order, separated by the greater than ('>') character.

For each state, a context may be indicated by the plus ('+') character followed by the context name.

Lastly, for every Action Group defined above, an exit version may be defined by adding an asterisk ('*') character to the end.

So, using the same example, these are the Action Group names the plugin will attampt to execute:

	HouseState
	HouseState|Away>Work+Dark*
	HouseState|Away>Work*
	HouseState|Away+Dark*
	HouseState|Away*
	HouseState|Home
	HouseState|Home+Dark
	HouseState|Home>Wake
	HouseState|Home>Wake+Dark
	HouseState*

Again, ***any Action Group that does not exist will be silently skipped***. You can create whichever ones make sense for you and ignore the rest.

When contexts are changed, the plugin will update every state in the hierarchy to reflect the change.  

Let's say that the context 'Rain' is added after the above state change occurs.  The following Actions Groups will be executed (if they exist):

	HouseState+Rain
	HouseState|Home+Rain
	HouseState|Home>Wake+Rain

And now let's say that morning breaks and the 'Dark' context is removed:

	HouseState|Home>Wake+Dark*
	HouseState|Home+Dark*
	HouseState+Dark*

## Variables

#### State Variables

The plugin will also create and maintain Variables for every state. Variable names will follow Action Group names, but with all the special characters replaced with the underscore ('_') character.

After the above state change, the variables will be:

	HouseState_Away				False
	HouseState_Away_Vacation	False
	HouseState_Away_Work		False
	HouseState_Home				True
	HouseState_Home_Sleep		False
	HouseState_Home_Wake		True

This makes it very easy to refer to the current state, or any of it's parent-states in conditional for Schedules and Triggers.

#### Other Variables

The plugin maintains a few other Variables as well.

A variable with the same name a the Base Name always holds the current state:

	HouseState					Home>Wake

There is a variable to store contexts _(note the double-underscore)_:

	HouseState__Context			[u'Dark',u'Rain']

And another for a time stamp _(note the double-underscore)_:

	HouseState__LastChange		2016-12-17 20:44:04.313000

---

## Installation

Install like any other Indigo Plugin.

## Configuration

#### Folder for Variables

Enter a name for the folder where the plugin's variables will be stored.  The folder will be created if it doesn't exist.

If you change folders, variables will be migrated to the new folder ***as they are accessed***.  Variables may be moved manually to the new folder.

#### Log Missing Action Groups

If checked, any Action Group that doesn't exist will be written to the log.  This is a handy way to get names of additional Action Groups that you may wish to create.

#### Enable Debugging

If checked, extensive debug information will be written to the log.

## Usage

### Defining Namespaces

Use the plugin's menu items to add or remove namespaces. Removed namespaces will not delete anything, but will cause existing actions to fail validation.

### Actions

The plugin defines new **actions**, but no new devices or triggers.

##### Enter New State

_Base Name_: the namespace of the state tree.

_New State_: the new state the system should enter.  Should be in state1>state2>state3 format.  Do not include any contexts.

##### Add Context

_Base Name_: the namespace of the state tree.

_Context_: The context to be added.  Do ***not*** includ the plus ('+') character.

##### Remove Context

_Base Name_: the namespace of the state tree.

_Context_: The context to be removed.  Do ***not*** includ the plus ('+') character.
