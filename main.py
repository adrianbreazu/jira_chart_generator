from jira import JIRA
import json
import logging
import os
import re
from multiprocessing import Lock, Process, Queue, current_process
import queue
import time

MANIFEST_JSON = ""
JIRA_URL = ""
JIRA_USER = ""
JIRA_PASSWORD = ""
TH_JIRA_CONNECTION = None


def get_credentials():
    global JIRA_URL
    global JIRA_USER
    global JIRA_PASSWORD
    global MANIFEST_JSON

    with open("manifest.json") as f:
        MANIFEST_JSON = json.load(f)
    with open(MANIFEST_JSON["access"]) as _f:
        access_json = json.load(_f)

    JIRA_URL = access_json["server_url"]
    JIRA_USER = access_json["username"]
    JIRA_PASSWORD = access_json["password"]


def connect ():
    try:
        log.info("Connecting to JIRA: {0}".format(JIRA_URL))
        jira_options = {'server': JIRA_URL}
        jira = JIRA(options=jira_options, auth=(JIRA_USER, JIRA_PASSWORD))
        log.info("Connection established")
        return jira
    except Exception as e:
        log.error("Failed to connect to JIRA: {0}".format(e))
        return None


def get_project_versions(jira_connector, project_name, regex_version):
    """
    Output: A dict containg an array of versions. 
        The dictionary is composed of released and unreleased versions. Each value in the dict contains the following structure
            'self': 'http:.........../1234567890'
			'id': '12334567890',
            'description': 'DESCRIPTION HERE',
			'name': 'VERSION_HERE',
			'archived': False,
			'released': True,
            'overdue': False
			'startDate': '2017-04-03',
			'releaseDate': '2017-05-12',
			'userStartDate': '03/Apr/17',
			'userReleaseDate': '12/May/17',
			'projectId': 1234567
    """

    versions_dict = {}
    unreleased_array = []
    released_array = []

    for version in jira_connector.project_versions(jira_connector.project(str(project_name))):
        if re.match(re.compile(str(regex_version)),str(version)):
            if (version.released):
                log.debug("released: {0}".format(version.name))
                released_array.append(version.raw)
            else:
                log.debug("unreleased: {0}".format(version.name))
                unreleased_array.append(version.raw)
    versions_dict["released"] = released_array
    versions_dict["unreleased"] = unreleased_array

    log.info("for project: {0} with regex: {1} we have version_dict: {2}".format(project_name, regex_version, versions_dict))
    return versions_dict
    

def process_version_data(project_name, version):
    """
        Output: create a CSV file for each verssion
    """
    path = "/".join([MANIFEST_JSON['data_storage_path'], str(project_name.replace(' ','_'))])
    try:
        if not os.path.exists(path):
            os.makedirs(path)
    except OSError:
        # because thread implementation
        pass
    file_name = ''.join(["Version_",str(version['name'].replace(' ', '_')),'.csv'])

    m = open('/'.join([path, file_name]), 'w+')
    m.write(','.join(["name","released", "startDate", "releaseDate", "userStartDate", "userReleaseDate"]))
    m.write('\r\n')
    
    log.debug('Extracted milestone data for value:{0}'.format(version['name']))
    version_data =[]
    version_data.append(version['name'])
    version_data.append(str(version['released']))

    if ('startDate' in version):
        version_data.append(str(version['startDate']))
    else:
        version_data.append("")

    if ('releaseDate' in version):
        version_data.append(str(version['releaseDate']))
    else:
        version_data.append("")

    if ('userStartDate' in version):
        version_data.append(str(version['userStartDate']))
    else:
        version_data.append("")

    if ('userReleaseDate' in version):
        version_data.append(str(version['userReleaseDate']))
    else:
        version_data.append("")
    
    log.debug('Extracted milestone: {0}, data :{1}'.format(version['name'], version_data))

    m.write(','.join(version_data))
    m.write('\r\n')
    m.close()
    

def collect_version_tickets(jira_connector, project_name, special_filters, versions):
    """
        Output: Array of JIRA Issue objects
    """
    _filter = " AND ".join(special_filters)
    #log.debug("project name:{0}, special_filters:{1}, versions:{2}, _filter:{3}, project_name[0]:{4}, len(project_name):{5}".format(project_name,special_filters,versions,_filter,project_name[0],len(project_name)))
    if (len(project_name) == 1):
        base_url = "project =  " + project_name[0] + " AND " + _filter + " AND fixVersion = \"" + versions + "\""
    else:
        base_url = "project in (" + ','.join(project_name) + ") AND " + _filter + " AND fixVersion = \"" + versions + "\""
    log.debug("Collect version issues for URL: {0}".format(base_url))
    
    log.debug ("base_url: {0}".format(base_url))
    jira_array = []

    jira_array = jira_connector.search_issues(jql_str=base_url, maxResults=None)
    log.info("version: {0} has {1} issues".format(versions, len(jira_array)))

    return jira_array


def process_jira_list(jira_connector, project_name, version_name, issue_array):
    """
        Output: create a CSV file with all the issues assigned to that version
    """
    path = "/".join([MANIFEST_JSON['data_storage_path'], str(project_name.replace(' ','_'))])
    if not os.path.exists(path):
        os.makedirs(path)
    file_name = ''.join([str(version_name.replace(' ', '_')),'.csv'])
    
    f = open('/'.join([path,file_name]),'w+')
    
    f.write(','.join(["KEY","Resolution","labels","creationDate","resolutionDate","Priority_cust","assignee","status","issueType", "components_list", "epic_link", "sprint_list", "sprintStartDate_list","sprintEndDate_list","sprintCompleteDate_list"]))
    f.write('\r\n')
    #Create jira tickets file
    for issue in issue_array:
        issue_data=[]
        issue_data.append(issue.key)
        log.debug('Extracted issue.key value:{0}'.format(issue.key))
        if (issue.fields is not None):
            if (issue.fields.resolution is not None):
                if (issue.fields.resolution.name is not None):
                    issue_data.append(issue.fields.resolution.name)
                    log.debug('Extarcted issue.fields.resolution.name value: {0}'.format(issue.fields.resolution.name))
                else:
                    issue_data.append('')
            else:
                issue_data.append('')

            if (issue.fields.labels is not None):
                issue_data.append(';'.join(issue.fields.labels))
                log.debug('Extarcted issue.fields.labels value: {0}'.format(issue.fields.labels))
            else:
                issue_data.append('')
            if (issue.fields.created is not None):
                issue_data.append(issue.fields.created)
                log.debug('Extarcted issue.fields.created value: {0}'.format(issue.fields.created))
            else:
                issue_data.append('')
            if (issue.fields.resolutiondate is not None):
                issue_data.append(issue.fields.resolutiondate)
                log.debug('Extarcted issue.fields.resolutiondate value: {0}'.format(issue.fields.resolutiondate))
            else:
                issue_data.append('')

            if (issue.fields.customfield_10070 is not None):
                if (issue.fields.customfield_10070.value is not None):
                    issue_data.append(issue.fields.customfield_10070.value)
                    log.debug('Extarcted issue.fields.customfield_10070.value value: {0}'.format(issue.fields.customfield_10070.value))
                else:
                    issue_data.append('')
            else:
                issue_data.append('')
            if (issue.fields.assignee is not None):
                if (issue.fields.assignee.name is not None):
                    issue_data.append(issue.fields.assignee.name)
                    log.debug('Extarcted issue.fields.assignee.name value: {0}'.format(issue.fields.assignee.name))
                else:
                    issue_data.append('')
            else:
                issue_data.append('')

            if (issue.fields.status is not None):
                if (issue.fields.status.name is not None):
                    issue_data.append(issue.fields.status.name)
                    log.debug('Extarcted issue.fields.status.name value: {0}'.format(issue.fields.status.name))
                else:
                    issue_data.append('')
            else:
                issue_data.append('')

            if (issue.fields.issuetype is not None):
                if (issue.fields.issuetype.name is not None):
                    issue_data.append(issue.fields.issuetype.name)
                    log.debug('Extarcted issue.fields.issuetype.name value: {0}'.format(issue.fields.issuetype.name))
                else:
                    issue_data.append('')
            else:
                issue_data.append('')
            
            if (issue.fields.components is not None):
                component_list = []
                for component in issue.fields.components:
                    component_list.append(str(component.name))
                issue_data.append(";".join(component_list))
            else:
                issue_data.append('')

            if (issue.fields.customfield_11480 is not None):
                issue_data.append(issue.fields.customfield_11480)
            else:
                issue_data.append('')

            if (issue.fields.customfield_10880 is not None):
                s_name = []
                s_startdate = []
                s_enddate = []
                s_completedate = []
                for val in issue.fields.customfield_10880:
                    sprint_name = re.findall(r"name=[^,]*", val)[0].replace("name=",'')
                    s_name.append(sprint_name)
                    start_date = re.findall(r"startDate=[^,]*", val)[0].replace("startDate=",'')
                    s_startdate.append(start_date)
                    end_date = re.findall(r"endDate=[^,]*", val)[0].replace("endDate=",'')
                    s_enddate.append(end_date)
                    complete_date = re.findall(r"completeDate=[^,]*", val)[0].replace("completeDate=",'')
                    s_completedate.append(complete_date)
                issue_data.append(';'.join(s_name))
                issue_data.append(';'.join(s_startdate))
                issue_data.append(';'.join(s_enddate))
                issue_data.append(';'.join(s_completedate))
            else:
                issue_data.append(''*4)
        else:
            issue.append(''*10)
            log.error("issue.fields is empty for key: {0}".format(issue.key))

        log.debug('Extarcted issue_data value: {0}'.format(issue_data))
        f.write(','.join(issue_data))
        f.write('\r\n')
    f.close()


def collect_data():
    get_credentials()   
    jira_connector = connect()
    if (jira_connector != None):
        # get a dict with all released and unreleased version of the projects defined in the manifest.json file
        for project in MANIFEST_JSON["extract_for"]:
            _project_code = MANIFEST_JSON["extract_for"][project]["settings"]["project_code"]
            _special_filters = MANIFEST_JSON["extract_for"][project]["settings"]["special_filters"]
            project_versions_dict[project] = get_project_versions(jira_connector,
                                        _project_code[0],
                                        MANIFEST_JSON["extract_for"][project]["settings"]["regex_version"])
            log.info("Finish collecting versions for project: {0}".format(project))
            print("### Finish Versions for project: {0} ###".format(project))
            for released_unreleased in project_versions_dict[project]:
                for version in project_versions_dict[project][released_unreleased]:
                    # process version data 
                    process_version_data(project, version)
                    issue_array = []
                    issue_array = collect_version_tickets(jira_connector, _project_code, _special_filters, version['name'])
                    # process resulted array of Jira tickets
                    process_jira_list(jira_connector, project, version['name'], issue_array)

                    print("### Finish collecting issues for version: {0} ###".format(version['name']))
                    log.info("Finish collecting issues for version: {0}".format(version['name']))
        log.debug("version dict:{0}".format(project_versions_dict))


def multithread_collect_data():
    global workQueue
    
    get_credentials()   
    TH_JIRA_CONNECTION = connect()
    number_of_threads = 4
    workQueue = Queue()
    processes = []

    if (TH_JIRA_CONNECTION != None):
        # get a dict with all released and unreleased version of the projects defined in the manifest.json file
        for project in MANIFEST_JSON["extract_for"]:
            _project_code = MANIFEST_JSON["extract_for"][project]["settings"]["project_code"]
            _special_filters = MANIFEST_JSON["extract_for"][project]["settings"]["special_filters"]
            project_versions_dict[project] = get_project_versions(TH_JIRA_CONNECTION,
                                        _project_code[0],
                                        MANIFEST_JSON["extract_for"][project]["settings"]["regex_version"])
            log.info("Finish collecting versions for project: {0}".format(project))
            print("### Finish Versions for project: {0} ###".format(project))

            for released_unreleased in project_versions_dict[project]:
                for version in project_versions_dict[project][released_unreleased]:
                    version["project_code"] = _project_code
                    version["manifest_project_name"] = project
                    version["special_filters"] = _special_filters
                    workQueue.put(version)
                    log.info("Finish adding version data to work queue: {0}".format(version))
                    
        log.debug("version dict:{0}".format(project_versions_dict))
    else:
        log.error("TH_JIRA_CONNECTION is None !!! in multithread_collect_data")

    for w in range(number_of_threads):
        p = Process(target=multithread_process_data,args=(current_process().name, workQueue))
        processes.append(p)
        p.start()
        print("Process: {0} is being created with id: {1}".format(p.name, p.pid))
        log.debug("Process: {0} is being created with id: {1}".format(p.name, p.pid))
        

    for p in processes:
        p.join()
        log.debug("join thread: {0}".format(p))
    
    log.info("EXIT MAIN THREAD")


def multithread_process_data(mainThread, _work_queue):
    get_credentials()   
    TH_JIRA_CONNECTION = connect()

    if (TH_JIRA_CONNECTION is not None):
        while True:
            try:
                data = _work_queue.get_nowait()
                project_code = data["manifest_project_name"]
                print("{0}, with id {1}, is processing version {2}".format(current_process().name, current_process().pid, data["name"]))
                process_version_data(project_code, data)
                issue_array = []
                issue_array = collect_version_tickets(TH_JIRA_CONNECTION, data["project_code"], data["special_filters"], data['name'])
                process_jira_list(TH_JIRA_CONNECTION, data["manifest_project_name"], data['name'], issue_array)

            except queue.Empty:
                break

        return True


def main():
    #collect_data()
    multithread_collect_data()


if __name__ == "__main__":
    project_versions_dict = {}
    print("### START ###")
    log = logging.getLogger(__name__)
    
    if not os.path.exists('logs'):
        os.makedirs('logs')

    logging.basicConfig(filename='logs/log_data.log',level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    main()
    print("###  DONE  ###")