#/***********************************************************************
# * Licensed Materials - Property of IBM 
# *
# * IBM SPSS Products: Statistics Common
# *
# * (C) Copyright IBM Corp. 1989, 2014
# *
# * US Government Users Restricted Rights - Use, duplication or disclosure
# * restricted by GSA ADP Schedule Contract with IBM Corp. 
# ************************************************************************/#Licensed Materials - Property of IBM


# Extension command for selecting variables and defining a macro
from __future__ import with_statement

__author__  =  'spss, jkp'
__version__ =  '1.3.1'
version = __version__

# history
# 19-mar-2010  initial version
#  01-jul-2010 added ROLE keyword
#  4-may-2012 add support for TO and ALL in variable list
#  04-feb-2014 handle huge variable lists
#  17-feb-2014 force a blank in separator for text wrapping
#  05-mar-2014 fix problem with case mismatch in expand call
#  07-mar-2014 support ALL with a list of variable names.  Add ASLISTED
#  30-nov-2014 fix bad translation call in pivot table title

# Notes:
# In Unicode mode, if there are extended characters in the variable names, it
# requires at least version 2.5.1 of spssaux.py and Statistics 18.0.2.

import textwrap

helptext="""SPSSINC SELECT VARIABLES MACRONAME="macroname" [VARIABLES=varlist]
[/PROPERTIES 
  [TYPE= {NUMERIC|STRING}]
  [LEVEL= NOMINAL ORDINAL SCALE UNKNOWN]
  [PATTERN = "name regular expression"]
  [ROLE=ANY* INPUT TARGET BOTH NONE PARTITION SPLIT
[/ATTRHASANY list-of-attribute-names]
[/ATTRHASALL list-of-attribute-names]
[/ATTRVALUES NAME=name VALUE="value" "value" ...
NAME1 ... NAME5 and VALUE1 ... VALUE5 repeat the structure of NAME and VALUE]
[/OPTIONS
  [IFNONE={ERROR*|CREATE}]]
  [ORDER={ALPHA*|FILE|ASLISTED}
  [PRINT={YES*|NO}]]
  [SEPARATOR="text"]
[/HELP]

Example:
SPSSINC SELECT VARIABLES MACRONAME="allnumeric"
/PROPERTIES TYPE+NUMERIC.

This command defines an SPSS macro whose contents are the names of all variables
that meet the specified variable dictionary-based selection criteria.

The variable list defaults to ALL.  TO and ALL can be used in the variable list.
If ALL is used, it must be last.  All variables will be appended to other
listed variables if not already listed.

MACRONAME specifies the name of the generated macro.  By convention, macro
names should start with "!".  It must be enclosed in quotes.

An optional variable list restricts the result to a subset of the listed variables.
If no variable list is given, the selection criteria are applied to all of the variables.
Note that variable names are case sensitive.

TYPE, LEVEL, and PATTERN optionally specify further restrictions.
TYPE can be NUMERIC or STRING.
LEVEL can be one or more of the four measurement levels.
PATTERN is a case-insensitive regular expression to be applied to the names.
It must be enclosed in quotes.
The pattern starts at the beginning of the name.
    Examples:
        'age'  - any variables starting with age
        '.*age'- any variable whose name contains age
        '.*\d$' - any variable whose name ends in a digit
        
In Statistics Version 18 or later, the variable role can be used to restrict the
list by specifying ROLE.  ROLE is typically a single item, but multiple roles
can be listed.  This is particularly useful in IBM SPSS Modeler.  
In version 17, the role criterion is ignored.

The three attribute subcommands specify restrictions based on variable attributes.
Variable attributes are typically created with the VARIABLE ATTRIBUTE command.
Attribute names listed on /ATTRHASANY mean that a variable must have at least
one of the attribute names listed to qualify.  The attribute value does not matter.

Attribute names listed on /ATTRHASALL mean that a variable must have all of
the listed attributes to qualify.

/ATTRVALUES specifies pairs of attribute names and value lists.  For each
pair, if the variable has the named attribute, the attribute value must be one
of the values listed for that attribute.  If the variable does not have the attribute,
the test is ignored.
Examples:
/ATTRVALUES NAME=CLASS VALUES="bird" "fish" NAME1=REGION VALUE1="Asian".
For variables with the attribute CLASS , the attribute value must be "bird" or "fish"
and variables with the attribute REGION must have an attribute value of "Asian"

Pairs are indicated by the suffix on the name and value keywords.

The attribute names are not case sensitive, but the values, 
which must be enclosed in quotes, are.

For array attributes, a variable qualifies if any array value matches any of
the listed values.

OPTION ORDER specifies the order of the selected variables in the macro
definition.  The list can be sorted alphabetically or by the file order 
of the variables.  If ORDER=ASLISTED, no sorting is done, so named
variables will appear in that order, but ALL or property-selected
variables will be in an arbitrary order.

PRINT specifies whether or not to print a table listing the variables in the macro.

IFNONE specifies whether to raise an error if no variables qualify or to
define an empty macro.

SEPARATOR defines what character or string of characters is inserted
between variable names in the macro.  By default it is a blank, but "+"
could be useful for building CTABLES table expressions.

For Python programmers, a dictionary accessible from other modules is
maintained holding the definitions of all the macros generated by this
procedures.  It can be accessed as 
SPSSINC_SELECT_VARIABLES.macrodict["macroname"]
after importing the module.
"""

import inspect, re, copy, sys
import spss, spssaux
from extension import Template, Syntax, processcmd
ok1800 = spssaux.getSpssVersion() >=[18,0,0]

def Run(args):
    """Execute the SPSSINC SELECT VARIABLES command"""

    args = args[args.keys()[0]]
    ###print args   #debug

    oobj = Syntax([
        Template("VARIABLES", subc="",  ktype="existingvarlist", var="varnames", islist=True),
        Template("MACRONAME", subc="", ktype="literal", var="macroname"),
        Template("TYPE", subc="PROPERTIES",  ktype="str", var="vartype", vallist=["numeric","string"]),
        Template("LEVEL", subc="PROPERTIES", ktype="str", var="level", islist=True),
        Template("PATTERN", subc="PROPERTIES", ktype="literal", var="pattern"),
        Template("ROLE", subc="PROPERTIES", ktype="str", var="role", 
            vallist=["any", "input","target","both","none","partition","split"], islist=True),
        Template("IFNONE", subc="OPTIONS", ktype="str", var="ifnone", vallist=["error", "create"]),
        Template("ORDER", subc="OPTIONS", ktype="str", var="order", vallist=["alpha", "file", "aslisted"]),
        Template("PRINT", subc="OPTIONS", ktype="bool", var="printdef"),
        Template("SEPARATOR", subc="OPTIONS", ktype="literal", var="sep"),
        Template("", subc="ATTRHASANY", ktype="str", var="attrhasany", islist=True),
        Template("", subc="ATTRHASALL", ktype="str", var="attrhasall", islist=True),
        Template("NAME", subc="ATTRVALUES", ktype="str", var="attrname"),
        Template("VALUE", subc="ATTRVALUES", ktype="literal", var="value", islist=True),
        Template("NAME1", subc="ATTRVALUES", ktype="str", var="attrname1"),
        Template("VALUE1", subc="ATTRVALUES", ktype="literal", var="value1", islist=True),
        Template("NAME2", subc="ATTRVALUES", ktype="str", var="attrname2"),
        Template("VALUE2", subc="ATTRVALUES", ktype="literal", var="value2", islist=True),
        Template("NAME3", subc="ATTRVALUES", ktype="str", var="attrname3"),
        Template("VALUE3", subc="ATTRVALUES", ktype="literal", var="value3", islist=True),
        Template("NAME4", subc="ATTRVALUES", ktype="str", var="attrname4"),
        Template("VALUE4", subc="ATTRVALUES", ktype="literal", var="value4", islist=True),
        Template("NAME5", subc="ATTRVALUES", ktype="str", var="attrname5"),
        Template("VALUE5", subc="ATTRVALUES", ktype="literal", var="value5", islist=True)])

    #debugging
    #try:
        #import wingdbstub
        #if wingdbstub.debugger != None:
            #import time
            #wingdbstub.debugger.StopDebug()
            #time.sleep(2)
            #wingdbstub.debugger.StartDebug()
    #except:
        #pass

    #enable localization
    global _
    try:
        _("---")
    except:
        def _(msg):
            return msg

    # A HELP subcommand overrides all else
    if args.has_key("HELP"):
        #print helptext
        helper()
    else:
        processcmd(oobj, args, selectvariables)

def helper():
    """open html help in default browser window
    
    The location is computed from the current module name"""
    
    import webbrowser, os.path
    
    path = os.path.splitext(__file__)[0]
    helpspec = "file://" + path + os.path.sep + \
         "markdown.html"
    
    # webbrowser.open seems not to work well
    browser = webbrowser.get()
    if not browser.open_new(helpspec):
        print("Help file not found:" + helpspec)
try:    #override
    from extension import helper
except:
    pass        
        
def selectvariables(macroname, varnames=None, vartype=None, level=None, pattern=None,
        ifnone="error", order="alpha", printdef=True, sep=" ", role=["any"],
        attrhasany=None, attrhasall=None,
        attrname=None, value=None,
        attrname1=None, value1=None,
        attrname2=None, value2=None,
        attrname3=None, value3=None,
        attrname4=None, value4=None,
        attrname5=None, value5=None):
    
    # macrodict retains the most recent definition of any macro created by this function
    # for use by other Python code via SPSSINC_SELECT_VARIABLES.macrodict.
    # The value is cleared as soon as possible in the event of a redefinition.
    global macrodict
    # ensure that macrodict is defined as a module global
    try:
        type(macrodict)
    except:
        macrodict = {}
    try:
        del(macrodict[macroname])
    except:
        pass
    
    anames = [attrname, attrname1,attrname2,attrname3,attrname4,attrname5] #all lower case
    avals = [value, value1, value2,value3,value4,value5] #literal values.  Each is a list
    # attribute names and value lists must occur in pairs.
    if sum([(k is None) ^ (v is None) for k,v in zip(anames, avals)]) > 0:
        raise ValueError(_("The attribute name and value pairs on ATTRVALUES do not match"))
    avalsdict = dict([(e1, e2) for e1, e2 in zip(anames, avals) if not e1 is None])
    
    if not pattern is None:
        try:
            re.compile(pattern)  #throwaway just to see if valid and give better error message
        except:
            raise ValueError(_("Invalid pattern regular expression: %s") % sys.exc_info()[1].args[0])
    # TO and ALL support
    if varnames:
        varnames = expandvarnames(varnames)

    varnames = rolefilter(varnames, role)
    # delegate screen on selection criteria other than attributes and role to VariableDict
    vardict = spssaux.VariableDict(namelist=varnames, variableType=vartype, pattern=pattern,
        variableLevel=level, caseless=True)

    resultset = set(vardict)
    
    # attribute screening if required
    if attrhasall or attrhasany or avalsdict:
        if not attrhasall is None:
            attrhasall = set(attrhasall)
        else:
            attrhasall = set()
        if not attrhasany is None:
            attrhasany = set(attrhasany)
        else:
            attrhasany = set()
        removeset = set()
        
        for v in resultset:
            # get variable attributes.  array attributes are returned with name attrname[index]
            # convert values into a list of items.  Order has no meaning
            vattrs = dict([(k.lower(), val) for k, val in v.Attributes.items()])   # empty dict if no attributes
            listifyAttrs(vattrs)
            vattrset = set(vattrs)
            
            if attrhasall and not (attrhasall.issubset(vattrset)):
                removeset.add(v)
                continue
            if attrhasany and not attrhasany.intersection(vattrset):
                removeset.add(v)
                continue
            if avalsdict:  # if variable has the attribute but no value matches, discard variable
                for ak,av in avalsdict.items():
                    if ak in vattrs:   # variable has the attribute.  See if any value matches
                        for a in vattrs[ak]:      # vattrs[ak] is a list of values
                            if  a in av:  # av is a (short) list
                                break    # matched: keep the item
                        else:
                            removeset.add(v)    # no match was found: discard item
                            
        resultset.difference_update(removeset)
        
    if ifnone == "error" and not resultset:
        raise ValueError(_("No variables qualify for macro definition %s") % macroname)
    # sort in alpha or file order unless ASLISTED was specified
    if order == "alpha":
        resultlist = sorted((v.VariableName for v in resultset))
    elif order == "file":
        resultlist = sorted(((v.VariableIndex, v.VariableName) for v in resultset))
        resultlist = [v for i, v in resultlist]
    else:
        # aslisted - explicitly listed variables that passed filter come first
        resultlistset = set([v.VariableName for v in resultset])
        if varnames is None:
            resultlist = []
        else:
            resultlist = [v for v in varnames if v in resultlistset]
        resultlist.extend(resultlistset - set(resultlist))
        

    if not (sep.startswith(" ") or sep.endswith(" ")):
        sep = " " + sep
    lines = textwrap.wrap(sep.join(resultlist), width=150, break_long_words=False, break_on_hyphens=False)
    spss.SetMacroValue(macroname, "\n".join(lines))
    macrodict[macroname] = resultlist
    if printdef:
        # can't generate the ideal table here because can't put strings in cells
        tbl = NonProcPivotTable("INFORMATION", outlinetitle=_("Macro Definition"),
            tabletitle = _("Variables Listed in Macro %s") % macroname, columnlabels =[],
            procname = "SPSSINC SELECT VARIABLES")
        if not resultlist:
            resultlist = [_("No matching variables")]
        tbl.addrow(rowlabel = " ".join(resultlist))
        tbl.generate()

def expandvarnames(varnames):
    """Return varnames with ALL and TO expansion"""
    
    # varnames allows the construct v1, v2, ... ALL to coerce the order
    # as well as TO and ALL expansion
    vardict = None
    varnamesLower = [item.lower() for item in varnames]
    try:
        # check for and process ALL name
        allLoc = varnamesLower.index('all')
    except ValueError:
        allvars = []
    else:
        vardict = spssaux.VariableDict()
        if allLoc != len(varnames) -1:
            raise ValueError(_("""ALL must be the last item in the variable list"""))
        allvars = vardict.expand("ALL")
        varnames = varnames[:-1]

    # process TO
    if 'to' in varnamesLower:
        if not vardict:
            vardict = spssaux.VariableDict()
        varnames = vardict.expand(varnames)
    # append ALL result if it was specified
    # would use set union but order matters
    for item in allvars:
        if not (item in varnames or item.lower() in varnames):
            varnames.append(item)
    return varnames
        
def listifyAttrs(vattrs):
    """rationalize array attributes and convert all attributes into lists
    
    vattrs is the Attributes dictionary for a variable.
    array atributes appear as name[subscript] in the dictionary."""
    
    vattrlist = vattrs.items()
    for k, v in vattrlist:
        subscript = k.find("[")
        if subscript > 0:   # can't be 0
            root = k[:subscript]
            if not root in vattrs:
                vattrs[root] = []
            vattrs[root].append(v)
            del vattrs[k]
        else:
            vattrs[k] = [v]   # all values become lists

    
class NonProcPivotTable(object):
        """Accumulate an object that can be turned into a basic pivot table once a procedure state can be established"""
        
        def __init__(self, omssubtype, outlinetitle="", tabletitle="", caption="", rowdim="", coldim="", columnlabels=[],
                     procname="Messages"):
                """omssubtype is the OMS table subtype.
                caption is the table caption.
                tabletitle is the table title.
                columnlabels is a sequence of column labels.
                If columnlabels is empty, this is treated as a one-column table, and the rowlabels are used as the values with
                the label column hidden
                
                procname is the procedure name.  It must not be translated."""
                
                attributesFromDict(locals())
                self.rowlabels = []
                self.columnvalues = []
                self.rowcount = 0
        
        def addrow(self, rowlabel=None, cvalues=None):
            """Append a row labelled rowlabel to the table and set value(s) from cvalues.
            
            rowlabel is a label for the stub.
            cvalues is a sequence of values with the same number of values are there are columns in the table."""
                
            if cvalues is None:
                cvalues = []
            self.rowcount += 1
            if rowlabel is None:
                    self.rowlabels.append(str(self.rowcount))
            else:
                    self.rowlabels.append(rowlabel)
            if not _isseq(cvalues):
                    cvalues = [cvalues]
            self.columnvalues.extend(cvalues)
            
        def generate(self):
                """Produce the table assuming that a procedure state is now in effect if it has any rows."""
                
                privateproc = False
                if self.rowcount > 0:
                    import spss
                    try:
                            table = spss.BasePivotTable(self.tabletitle, self.omssubtype)
                    except:
                            spss.StartProcedure(self.procname)
                            privateproc = True
                            table = spss.BasePivotTable(self.tabletitle, self.omssubtype)
                    if self.caption:
                            table.Caption(self.caption)
                    # Note: Unicode strings do not work as cell values in 18.0.1 and probably back to 16
                    if self.columnlabels != []:
                            table.SimplePivotTable(self.rowdim, self.rowlabels, self.coldim, self.columnlabels, self.columnvalues)
                    else:
                            table.Append(spss.Dimension.Place.row,"rowdim",hideName=True,hideLabels=True)
                            table.Append(spss.Dimension.Place.column,"coldim",hideName=True,hideLabels=True)
                            colcat = spss.CellText.String("Message")
                            for r in self.rowlabels:
                                    cellr = spss.CellText.String(r)
                                    table[(cellr, colcat)] = cellr
                    if privateproc:
                            spss.EndProcedure()
def _isseq(obj):
        """Return True if obj is a sequence, i.e., is iterable.
        
        Will be False if obj is a string or basic data type"""
        
        if isinstance(obj, basestring):
                return False
        else:
                try:
                        iter(obj)
                except:
                        return False
                return True

def attributesFromDict(d):
    """build self attributes from a dictionary d."""

    # based on Python Cookbook, 2nd edition 6.18

    self = d.pop('self')
    for name, value in d.iteritems():
        setattr(self, name, value)

        
def rolefilter(varnames, role):
    """Return list of varnames filtered by role criteria
    
    varnames is a list of variable names or None
    role is a list of roles
    If not at least version 18, role filtering is ignored
    If no variables satisfy the criteria, a list with one blank item
    is returned, because VariableDict does not permit an empty list
    If a variable is undefined, an exception will be raised."""
    
    if not ok1800:
        return varnames
    if "any" in role:
        return varnames
    if varnames is None:
        roledict = getRole()
        varnames = roledict.keys()
    else:
        roledict = getRole(varnames)
    varnames = [v for v in varnames if roledict[v.lower()] in role]
    if varnames:
        return varnames
    else:
        return [""]
    
# getRole duplicated from spssaux2.py to avoid dependency

def getRole(varlist=""):
    """Return a dictionary of role settings for varlist
    
    varlist is a list of variables.  If not specified, roles for all variables are returned.
    
    The dictionary keys are the variable names lower cased.  They will be in 
    code page or Unicode depending on the Statistics mode.
    
    If the Statistics version is prior to 18, an exception will be raised."""
    
    if not ok1800:
        raise AttributeError("getRole api is not available prior to version 18")
    
    if varlist:
        varlist = "/VARIABLES=" + " ".join(varlist)
    spss.Submit(["PRESERVE.", "SET OLANG=ENGLISH."])
    tag, errlevel = spssaux.CreateXMLOutput("DISPLAY DICTIONARY " + varlist, 
        omsid='File Information')
    spss.Submit("RESTORE")
    if errlevel:
        raise ValueError("Invalid variable specification in getRole")
    
    variables =spss.EvaluateXPath(tag, "/",
        """//pivotTable[@subType="Variable Information"]/dimension/category/@varName""")
    rolelist = spss.EvaluateXPath(tag, "/",
        """//pivotTable[@subType="Variable Information"]/dimension/category/dimension/category[position() = 4]/cell/@text""")
    spss.DeleteXPathHandle(tag)
    variables = [v.lower() for v in variables]
    rolelist = [v.lower() for v in rolelist]
    return dict(zip(variables, rolelist))
    