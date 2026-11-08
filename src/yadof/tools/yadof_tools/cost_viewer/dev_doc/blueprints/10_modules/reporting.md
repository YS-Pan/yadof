# Module Blueprint: Reporting

`report.py` formats an ASCII-safe summary and aligned Pareto table from prepared
rows. Objective names appear in table headers without a redundant standalone
`objectives:` line. Reports include bounded ignored-issue details and the shown
versus total Pareto count. Reporting does not import Matplotlib or write files.
