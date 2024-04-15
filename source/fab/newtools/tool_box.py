##############################################################################
# (c) Crown copyright Met Office. All rights reserved.
# For further details please refer to the file COPYRIGHT
# which you should have received as part of this distribution
##############################################################################

'''This file contains the ToolBox class.
'''

from fab.newtools import Tool, ToolRepository


class ToolBox:
    '''This class implements the tool box. It stores one tool for each
    category to be used in a FAB build.
    '''

    def __init__(self):
        self._all_tools = {}

    def add_tool(self, category: str, tool: Tool):
        '''Adds a tool for a given category.

        :param category: the category for which to add a tool
        :param tool: the tool to add.
        '''
        self._all_tools[category] = tool

    def get_tool(self, category: str):
        '''Returns the tool for the specified category.

        :param category: the name of the category in which to look
            for the tool.

        :raises KeyError: if the category is not known.
        '''

        if category in self._all_tools:
            return self._all_tools[category]

        # No tool was specified for this category, get the default tool
        # from the ToolRepository
        tr = ToolRepository.get()
        return tr.get_default(category)
