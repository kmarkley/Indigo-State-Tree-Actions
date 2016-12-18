# State Tree Watcher

*(inspired by the variable-watcher.py example script here: http://wiki.indigodomo.com/doku.php?id=advanced_thermo)*

## Overview

This plugin creates actions to automate execution of multiple **Action Groups** based on a hierarchical tree-like structure of _states_.  Additional **Action Groups** are executed for each state depending on multiple inherited _contexts_.  The system is analogous to method hooks in software development.

Additionally the plugin creates and maintains multiple **Variables** that track each _state_ for use in **Schedule** and/or **Trigger** conditinals.

## Details

Imagine a simple set of nested/hierarchical _states_ like this:
`
HouseState
    Home
        Wake
        Sleep
    Away
        Work
        Vacation
`
