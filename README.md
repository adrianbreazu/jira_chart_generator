# Description
Generate custom JIRA charts based on extracted issue values. The system will extract all the JIRA versions, sprint and ticket information from the selected versions, store them into a sqlite db.
Based on the populated db a set of Agile Score charts are generated.
By default we used 4 threads to populate the sqlite db.
 

#TODO in order to make it work:
## 1. Upate json/connect/credentials.json
Update the credentials file by adding the correct:
- username
- password
- url

## 2. Update json/mapper/fileds.json
Please populate this to relfect your jira setup field mapping. In case a field is not used, leave it empty.

## 3. Update manifest.json
Update the manifest by adding the correct:
- project name - logical name for each project
- project_code - array of strings, that represents the project KEY values. Please make sure the first key represent the main project in case multiple keys are provided
- special_filters - array fo special filters, will be concatenated with AND when jira filter is creted
- regex_version - string, use a regular expression in order to filter from all the project versions, only the ones that are of interest. If empty it will extract all issues from all versions including the empty one.s
- kpis: a list of predefiend KPIs used for chart generation. Only the KPIS with value set to "true" are being generated.

## 4. Create jira database
- create the database by using the command : sqlite3 jira.db <jira_schema.sql

## 5. Run the extraction
- Runn command: Python3 main.py