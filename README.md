# Description
Generate custom JIRA charts based on issue versions and sprint. The system will extract all the JIRA versions and Jira ticket informations from the selected versions, store them in multiple CSV files.
Based on the CSV files generated a set of KPIs charts are generated.
We used 4 threads when generating the CSV files.
 

#TODO in order to make it work:
## 1. Upate connect/credentials.json
Update the credentials file by adding the correct:
- username
- password
- url

## 2. Update manifest.json
Update the manifest by adding the correct:
- project name - logical name used to create the directory structure for the CSV files. eg. "first_project_name"
- project_code - array of strings, that represents the project KEY values. Please make sure the first key represent the main project in case multiple keys are provided
- special_filters - array fo special filters, will be concatenated with AND when jira filter is creted
- regex_version - string, use a regular expression in order to filter from all the project versions, only the ones that are of interest
- kpis: a list of predefiend KPIs used for chart generation. Only the KPIS with value set to "true" are being generated.