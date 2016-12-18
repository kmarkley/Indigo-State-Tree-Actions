# State Tree Watcher

*(inspired by the variable-watcher.py example script here: http://wiki.indigodomo.com/doku.php?id=advanced_thermo)*

## Overview

This plugin creates actions to automate execution of multiple **Action Groups** based on a hierarchical tree-like structure of _states_.  Additional **Action Groups** are executed for each state depending on multiple inherited _contexts_.  The system is analogous to method hooks in software development.

Additionally the plugin creates and maintains multiple **Variables** that track each _state_ for use in **Schedule** and/or **Trigger** conditinals.

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

When changing from one state to another, plugin will traverse 'up' the hierarchy of states being exited, attempting to execute an Action Group at each step, then traverse 'down' the hierachy, atempting to execute mor Action Groups for each state entered.

Additionally, the plugin will attempt to execute a global enter and global exit Action Group any time there is any change in state.

In the example above, when switching from the 'Work' state to the 'Wake' state, the plugin will try to execute these Action Groups:

	Global Enter
	Exit 'Work'
	Exit 'Away'
	Enter 'Home'
	Enter 'Wake'
	Global Exit

#### Contexts

Additionally, the plugin modifies states with _contexts_.

Unlike states, contexts are not mutually-exclusive and are inherited by all states.

For example, you may be at work when it is dark, or at home when it is dark.  You may have guests when you are awake or asleep.

For every combination of states and contexts, both an enter Action Group and an exit Action Group may be executed.  

So again in the example above, when switching from the 'Work' state to the 'Wake' state when dark, the following Action Groups may be executed:

	Global Enter
	Exit 'Work/Dark'
	Exit 'Work'
	Exit 'Away/Dark'
	Exit 'Away'
	Enter 'Home'
	Enter 'Home/Dark'
	Enter 'Wake'
	Enter 'Wake/Dark'
	Global Exit

Importantly, *** any Action Group that does not exist will be silently skipped***.


## Naming Conventions

All this is accomplished using strict naming conventions for Action Groups.

Each state change must have a **Base Name** that defines the namespace for all Action Groups.  In the example above, theis is 'HouseState'.  This is also the name of the global enter Action Group.

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

Again, *** any Action Group that does not exist will be silently skipped***. You can create whichever ones make sense for you and ignore the rest.

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

The plugin will also create and maintain Variables for every state. Variable names will follow Action Group names, but with all the special characters replaced with the underscore ('_') character.

After the above state change, the variables will be:

	HouseState_Away				False
	HouseState_Away_Vacation	False
	HouseState_Away_Work		False
	HouseState_Home				True
	HouseState_Home_Sleep		False
	HouseState_Home_Wake		True

This makes it very easy to refer to the current state, or any of it's parent-states in conditional for Schedules and Triggers.

The plugin maintains a few other Variables as well.

A variable with the same name a the Base Name alwys holds the current state:

	HouseState					Home>Wake

There is a variable to store contexts:

	HouseState__Context			[u'Dark',u'Rain']

And another for a time stamp:

	HouseState__LastChange		2016-12-17 20:44:04.313000

