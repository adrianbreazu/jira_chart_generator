from jira import JIRA
from jira import JIRAError
import json
import logging
import os
import re
from multiprocessing import Lock, Process, Queue, current_process
import queue
import time
import sqlite3
from sqlite3 import Error

MANIFEST_JSON = ""
JIRA_URL = ""
JIRA_USER = ""
JIRA_PASSWORD = ""
DB_FILE =""
MAPPER_FILE=""
DB_CONNECTION = None
TH_JIRA_CONNECTION = None
# change this if you need to lower or increase the amount of threads, each extracting issues from a different version
NUMBER_OF_THREADS = 4
log = None
workQueue = None
FIELDS_JSON_DICT = {}

version_dict = {}
issues_populated_dict = {}

def get_credentials():
    """
    Description: Extract credential and mapper field data from the JSON files and store them a in dictionary
    """

    global JIRA_URL
    global JIRA_USER
    global JIRA_PASSWORD
    global DB_FILE
    global MANIFEST_JSON
    global FIELDS_JSON_DICT

    with open("manifest.json") as f:
        MANIFEST_JSON = json.load(f)
    with open(MANIFEST_JSON["access"]) as _f:
        access_json = json.load(_f)

    with open("json/mapper/fields.json") as _file:
        file_json = json.load(_file)
        FIELDS_JSON_DICT = file_json["issue"]

    JIRA_URL = access_json["server_url"]
    JIRA_USER = access_json["username"]
    JIRA_PASSWORD = access_json["password"]
    DB_FILE = MANIFEST_JSON["database"]
    MAPPER_FILE = MANIFEST_JSON["mapper"]


def connect_to_db():
    """
    Description: Establish connection to the SQLITE3 datbase
    """
    global DB_CONNECTION
    log.info("Try to connect to the database")
    try:
        DB_CONNECTION = sqlite3.Connection(DB_FILE)
        log.info("Successful connection to the database: {0}".format(DB_FILE))
    except Error as er:
        log.error("Connection to the database ERROR:{0}".format(er))
    

def disconnect_from_db():
    """
    Description: disconnect from the SQLITE3 datbase
    """

    global DB_CONNECTION
    if DB_CONNECTION:
        DB_CONNECTION.close()


def connect_to_jira ():
    """
    Description: Establish connection to jira instance using the credentials and URL provided in the JSON file
    """

    try:
        log.info("Connecting to JIRA: {0}".format(JIRA_URL))
        jira_options = {'server': JIRA_URL}
        jira = JIRA(options=jira_options, basic_auth=(JIRA_USER, JIRA_PASSWORD))
        log.info("Connection established")
        return jira
    except Exception as e:
        log.error("Failed to connect to JIRA: {0}".format(e))
        return None


def get_project_versions(jira_connector, project_name, regex_version):
    """
    Description: Generate a list of all versions, filtered by the regex provided on the JSON manifest file
    """

    versions_dict = {}
    version_array = []

    if (regex_version == ""):
        version_array.append("empty")
    for version in jira_connector.project_versions(jira_connector.project(str(project_name))):
        if re.match(re.compile(str(regex_version)),str(version)):
            store_version_to_db(version.raw)
            log.info("for project: {0} with regex: {1} we have identified version: {2}".format(project_name, regex_version, version.raw))
            version_array.append(version.raw["name"])
    
    versions_dict["version_name"] = version_array
    log.info("for project: {0} with regex: {1} we have the following versions: {2}".format(project_name, regex_version, versions_dict))
    return versions_dict


def store_version_to_db(dict_value):
    """
    Description: Populate the verison database with the data of all versions provided in the input dictionary. To assure updated data, all existing fields will be overwritten
    Jira output: jira output value: {'self': 'link.....', 'id': '1', 'name': 'name_here', 'archived': False, 'released': False, 'startDate': '2001-01-01', 'releaseDate': '2001-01-31', 'overdue': True, 'userStartDate': '01/Jan/01', 'userReleaseDate': '31/Jan/01', 'projectId': 1}
    """

    if (DB_CONNECTION is not None):
        log.info("ready to store in database version :{0}".format(dict_value))
        cur = DB_CONNECTION.cursor()
        cur.execute("Select * from version where version_id = ?", (dict_value["id"],))
        rows = cur.fetchall()
        if (len(rows) == 0 ):
            #create version
            cur.execute("INSERT INTO version(version_id, name, archived, released, start_date, released_date) values(?,?,?,?,?,?)",
            (dict_value["id"],dict_value["name"],dict_value["archived"],dict_value["released"],dict_value["startDate"],dict_value["releaseDate"],))
            DB_CONNECTION.commit()
            log.info("A new version successfully created {0}".format(cur.lastrowid))
        else:
            #update version
            cur.execute("UPDATE version  set name=?, archived=?, released=?, start_date=?, released_date=? WHERE version_id=?",
            (dict_value["name"],dict_value["archived"],dict_value["released"],dict_value["startDate"],dict_value["releaseDate"],dict_value["id"],))
            DB_CONNECTION.commit()
            log.info("An updated version successfully for ID: {0}".format(dict_value["id"]))
    else:
        log.error("unable to store version :{0}".format(dict_value))


def collect_version_issues(jira_connector, project_name, special_filters, version_name):
    """
        Description: Extact from Jira instance all issues under a version to be stored into the database
    """

    _filter = " AND ".join(special_filters)
    if (version_name == "empty"):
        base_url = "project =  " + project_name[0] + " AND " + _filter + " AND fixVersion is " + version_name
    else:
        if (len(project_name) == 1):
            base_url = "project =  " + project_name[0] + " AND " + _filter + " AND fixVersion = \"" + version_name + "\""
        else:
            base_url = "project in (" + ','.join(project_name) + ") AND " + _filter + " AND fixVersion = \"" + version_name + "\""
        log.debug("Collect version issues for URL: {0}".format(base_url))
    
    print("base_url: {0}".format(base_url))
    jira_array = []
    jira_array = jira_connector.search_issues(jql_str=base_url, maxResults=None)
    log.info("version: {0} has {1} issues".format(version_name, len(jira_array)))

    store_issue_in_db(jira_connector, jira_array)


def store_issue_in_db(jira_connector, jira_array):
    """
        Description: Prepare to store issue data based on jira extracted information and filtered based on the fields mentioned in the fields JSON file 
    """

    issue_dict = {}
    for issue in jira_array:
        issue_dict = issue.raw
            
        #Extract value for all necessary fields, and add it to issue dictionary to be stored in the database
        log.info("Raw issue value: {0}".format(issue_dict))
        for key, value in FIELDS_JSON_DICT.items():
            issues_populated_dict[key] = getJiraValue(jira_connector, issue_dict, value.split("."), key)

        log.info("Finihs compiling the issue dictionary with the following values: {0}, this will be stored to database".format(issues_populated_dict))

        store_issue_and_additional_tables_data(jira_connector, issues_populated_dict, issue_dict)
        

def store_issue_and_additional_tables_data(jira_connector, populated_dict, issue_dict):
    """
        Description: Store issue data into the database
    """

    if (DB_CONNECTION is not None):
        log.info("ready to store in database issue id :{0}".format(populated_dict["key"]))
        cur = DB_CONNECTION.cursor()
        cur.execute("Select id from issue where key = ?", (populated_dict["key"],))
        rows = cur.fetchall()
        
        project_id = store_project(populated_dict["project_code"])
        resolution_id = store_resolution(populated_dict["resolution"])
        status_id = store_status(populated_dict["status"])
        type_id = store_type(populated_dict["type"])
        if (len(rows) == 0 ):
            #create issue
            cur.execute("INSERT INTO issue(key, summary, epic_name, labels,creation_date,resolution_date,updated_date,start_date,due_date,priority,assignee,reporter,components,epic_link,story_points,tshirt_size,linked_theme, resolution_id, status_id, type_id, project_id, raw_value) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
             (populated_dict["key"],populated_dict["summary"],populated_dict["epic_name"],populated_dict["labels"],populated_dict["created_date"],populated_dict["resolution_date"],\
                 populated_dict["updated_date"],populated_dict["start_date"],populated_dict["due_date"],populated_dict["priority"],populated_dict["assignee"],populated_dict["reporter"],populated_dict["components"],populated_dict["epic_links"],\
                     populated_dict["story_points"],populated_dict["tshirt_size"],populated_dict["linked_theme"],\
                         resolution_id,status_id,type_id,project_id,str(issue_dict)))
            DB_CONNECTION.commit()
            id_value = cur.lastrowid
            log.info("A new issue successfully created {0}".format(cur.lastrowid))
        else:
            #update issue
            cur.execute("UPDATE issue set summary=?, epic_name=?, labels=?, creation_date=?, resolution_date=?, updated_date=?, start_date=?, due_date=?, priority=?, assignee=?, reporter=?, components=?, epic_link=?, story_points=?, tshirt_size=?, linked_theme=?, resolution_id=?, status_id=?, type_id=?, project_id=?, raw_value=? WHERE key = ?",
             (populated_dict["summary"],populated_dict["epic_name"],populated_dict["labels"],populated_dict["created_date"],populated_dict["resolution_date"],\
                 populated_dict["updated_date"],populated_dict["start_date"],populated_dict["due_date"],populated_dict["priority"],populated_dict["assignee"],populated_dict["reporter"],populated_dict["components"],populated_dict["epic_links"],\
                     populated_dict["story_points"],populated_dict["tshirt_size"],populated_dict["linked_theme"],\
                         resolution_id,status_id,type_id,project_id,str(issue_dict),populated_dict["key"]))
            DB_CONNECTION.commit()            
            
            cur.execute("Select id from issue where key = ?", (populated_dict["key"],))
            rows = cur.fetchall()
            id_value = rows[0][0]
            log.info("An updated issue successfully for issue db id: {0} with key: {1}".format(id_value, populated_dict["key"]))
        
        #create issue_sprint records based on array populated_dict["sprints"] and returned issue db id
        store_issue_sprints(id_value, populated_dict["sprints"])
        store_issue_fix_version(id_value, populated_dict["fix_version"])
        store_issue_affects_version(id_value, populated_dict["affects_version"])

    else:
        log.error("unable to store issue with values:{0}".format(populated_dict))


def store_issue_sprints(value, sprint_list):
    """
        Description: Store issue-sprint relation data into the database
    """

    if (DB_CONNECTION is not None):
        log.info("ready to store in database issue_sprints, issue id:{0} and sprint list: {1}".format(value, sprint_list))
        if sprint_list != "":
            for item in sprint_list.split(','):
                cur = DB_CONNECTION.cursor()
                cur.execute("Select * from issue_sprints where issue_id = ? and sprint_id=?", (value,item))
                rows = cur.fetchall()
                if (len(rows) == 0 ):
                    #create issue_sprints
                    cur.execute("INSERT INTO issue_sprints (issue_id, sprint_id) values(?,?)", (value,item))
                    DB_CONNECTION.commit()
                    id_value = cur.lastrowid
                    log.info("A new record created for issue_sprints id:{0} for issue id: {1} and sprint id: {2}".format(id_value,value, item))
                else:
                    log.info("Already existins issue_sprint record with issue id: {0} and sprint id: {1}".format(value, item))
        else:
            log.info("Unable to add issue_sprint record with issue id: {0} and sprint id: {1}".format(value, sprint_list))
    else:
        log.error("unable to store issue_sprints with issue id: {0} and sprint: {1}".format(value, sprint_list))


def store_issue_fix_version(id_sprint, version_csv):
    """
        Description: Store issue-fixversion relation data into the database
    """

    if (DB_CONNECTION is not None):
        log.info("ready to store in database issue_fix_version, issue id:{0} and sprint list: {1}".format(id_sprint, version_csv))
        if version_csv != "":
            for item in version_csv.split(','):
                cur = DB_CONNECTION.cursor()
                cur.execute("Select id from version where name = ?", (item,))
                rows = cur.fetchall()
                if (len(rows) > 0):
                    version_id = rows[0][0]
                    cur = DB_CONNECTION.cursor()
                    cur.execute("Select * from issue_fix_version where issue_id = ? and version_id=?", (id_sprint,version_id))
                    rows = cur.fetchall()
                    if (len(rows) == 0 ):
                        #create issue_fix_version
                        cur.execute("INSERT INTO issue_fix_version (issue_id, version_id) values(?,?)", (id_sprint,version_id))
                        DB_CONNECTION.commit()
                        id_value = cur.lastrowid
                        log.info("A new record created for issue_fix_version with id{0} for issue id: {1} and version id: {2}".format(id_value, id_sprint, version_id))
                    else:
                        log.info("Already existins issue_fix_version record with issue id: {0} and version id: {1}".format(id_sprint, version_id))
                else:
                    log.error("unable to locate version name: {0} for sprint: {1}".format(item, id_sprint))
        else:
            log.info("Unable to add issue_fix_version record with issue id: {0} and versio name(s): {1}".format(id_sprint, version_csv))
    else:
        log.error("unable to add issue_fix_version record with issue id: {0} and versio name(s): {1}".format(id_sprint, version_csv))


def store_issue_affects_version(id_sprint, version_csv):
    """
        Description: Store issue-affectsversion relation data into the database
    """

    if (DB_CONNECTION is not None):
        log.info("ready to store in database issue_affects_version, issue id:{0} and sprint list: {1}".format(id_sprint, version_csv))
        if version_csv != "":
            for item in version_csv.split(','):
                cur = DB_CONNECTION.cursor()
                cur.execute("Select id from version where name = ?", (item,))
                rows = cur.fetchall()
                if (len(rows) > 0):
                    version_id = rows[0][0]                    
                    cur = DB_CONNECTION.cursor()
                    cur.execute("Select * from issue_affects_version where issue_id = ? and version_id=?", (id_sprint,version_id))
                    rows = cur.fetchall()
                    if (len(rows) == 0 ):
                        #create issue_affects_version
                        cur.execute("INSERT INTO issue_affects_version (issue_id, version_id) values(?,?)", (id_sprint,version_id))
                        DB_CONNECTION.commit()
                        id_value = cur.lastrowid
                        log.info("A new record created for issue_affects_version with id{0} for issue id: {1} and version id: {2}".format(id_value, id_sprint, version_id))
                    else:
                        log.info("Already existins issue_affects_version record with issue id: {0} and version id: {1}".format(id_sprint, version_id))
                else:
                    log.error("unable to locate version name: {0} for sprint: {1}".format(item, id_sprint))
        else:
            log.info("Unable to add issue_affects_version record with issue id: {0} and versio name(s): {1}".format(id_sprint, version_csv))
    else:
        log.error("unable to add issue_affects_version record with issue id: {0} and versio name(s): {1}".format(id_sprint, version_csv))


def store_project(value):
    """
        Description: Store project data into the database
    """

    if (DB_CONNECTION is not None):
        log.info("ready to store in database project, code :{0}".format(value))
        cur = DB_CONNECTION.cursor()
        cur.execute("Select id from project where project_id = ?", (value,))
        rows = cur.fetchall()
        if (len(rows) == 0 ):
            #create project
            cur.execute("INSERT INTO project (project_id) values(?)", (value,))
            DB_CONNECTION.commit()
            id_value = cur.lastrowid
            log.info("A new project was successfully created with db id: {0}, project code: {1}".format(id_value, value))
        else:
            id_value = rows[0][0]
    else:
        log.error("unable to store project with code: {0}".format(value))

    return id_value


def store_resolution(value):
    """
        Description: Store resolution data into the database
    """

    if (DB_CONNECTION is not None):
        log.info("ready to store in database resolution, value :{0}".format(value))
        cur = DB_CONNECTION.cursor()
        cur.execute("Select id from resolution where name = ?", (value,))
        rows = cur.fetchall()
        if (len(rows) == 0 ):
            #create resolution
            cur.execute("INSERT INTO resolution (name) values(?)", (value,))
            DB_CONNECTION.commit()
            id_value = cur.lastrowid
            log.info("A new resolution was successfully created with db id: {0}, project code: {1}".format(id_value, value))
        else:
            id_value = rows[0][0]
    else:
        log.error("unable to store resolution with name: {0}".format(value))

    return id_value


def store_status(value):
    """
        Description: Store status data into the database
    """

    if (DB_CONNECTION is not None):
        log.info("ready to store in database status, value :{0}".format(value))
        cur = DB_CONNECTION.cursor()
        cur.execute("Select id from status where name = ?", (value,))
        rows = cur.fetchall()
        if (len(rows) == 0 ):
            #create status
            cur.execute("INSERT INTO status (name) values(?)", (value,))
            DB_CONNECTION.commit()
            id_value = cur.lastrowid
            log.info("A new status was successfully created with db id: {0}, project code: {1}".format(id_value, value))
        else:
            id_value = rows[0][0]
    else:
        log.error("unable to store status with name: {0}".format(value))

    return id_value


def store_type(value):
    """
        Description: Store type data into the database
    """

    if (DB_CONNECTION is not None):
        log.info("ready to store in database type, value :{0}".format(value))
        cur = DB_CONNECTION.cursor()
        cur.execute("Select id from type where name = ?", (value,))
        rows = cur.fetchall()
        if (len(rows) == 0 ):
            #create type
            cur.execute("INSERT INTO type (name) values(?)", (value,))
            DB_CONNECTION.commit()
            id_value = cur.lastrowid
            log.info("A new type was successfully created with db id: {0}, project code: {1}".format(id_value, value))
        else:
            id_value = rows[0][0]
    else:
        log.error("unable to store type with name: {0}".format(value))

    return id_value


def getJiraValue(jira_connector, dict, element_list, key):
    """
        Description: Get the necessary issue fields data from the Jira issue output
    """
    
    value = None
    temp_dict = {}
    sprint_regex = r"id=([\d*]*)"

    try:
        if (len(element_list) == 1):
            value = dict[element_list[0]]
        else:
            temp_dict = dict[element_list[0]]
            for item in element_list[1:-1]:
                temp_dict = temp_dict[item]

            #extract comma separated string from array input, see fields.json additiona_comments
            if (element_list[-1][-2:] == "[]"):
                value_array = []
                for item in temp_dict:
                    value_array.append(item[element_list[-1][:-2]])
                value = ",".join(value_array)
            else:
                #populate Sprint table and return int array with sprint db ids
                value = temp_dict[element_list[-1]]
                if key == "sprints" and value is not None:
                    sprint_ids = re.findall(sprint_regex, "|".join(value))
                    log.info("The following sprints were identified {0}, from string {1}, with regex {2}".format(sprint_ids, value, sprint_regex))
                    value = store_sprint_data(jira_connector, sprint_ids)
                
    except KeyError as ke:
        value = ""
        log.warning("KeyError unable to extract value for Key: {0}, error recived: {1}".format(key, ke))
    except Exception as e:
        value = ""
        log.error("Exception unable to extract value for Key: {0}, error recived: {1}".format(key, e))
    finally:
        if (isinstance(value, str)):
            return value
        else:
            if (value is None):
                return ""
            else:
                return ",".join(value)


def store_sprint_data(jira_connector, sprint_ids):
    """
        Description: Extract sprint data from jira (based on sprint_id) and store it into the database
        Jira returned json: {'id': 1, 'sequence': 1, 'name': 'Sprint 1', 'state': 'CLOSED', 'linkedPagesCount': 0, 'goal': '....', 'startDate': '1/Jan/01 1:01 AM', 'endDate': '15/Jan/01 1:01 AM', 'isoStartDate': '2001-01-01T01:01:00+0000', 'isoEndDate': '2001-01-15T01:01:00+0000', 'completeDate': '16/Jan/01 1:01 AM', 'isoCompleteDate': '2001-01-16T01:01:07+0000', 'canUpdateSprint': True, 'remoteLinks': [], 'daysRemaining': 0}
    """

    sprint_dict = {}
    sprint_db_ids = []

    for id in sprint_ids:
        sprint_dict = jira_connector.sprint_info(None, id)
        log.info("Following sprint data was identified {0} for sprint id:{1}".format(sprint_dict, id))
        try:
            if (DB_CONNECTION is not None):
                log.info("ready to store in database sprint id :{0}".format(id))
                cur = DB_CONNECTION.cursor()
                cur.execute("Select * from sprint where sprint_id = ?", (id,))
                rows = cur.fetchall()
                if (len(rows) == 0 ):
                    #create sprint
                    cur.execute("INSERT INTO sprint(sprint_id, name, sequence, state, goal, start_date, end_date, complete_date) values(?,?,?,?,?,?,?,?)",
                    (sprint_dict["id"],sprint_dict["name"], sprint_dict["sequence"], sprint_dict["state"], sprint_dict["goal"],sprint_dict["startDate"],sprint_dict["endDate"], sprint_dict["completeDate"],))
                    DB_CONNECTION.commit()
                    id_value = cur.lastrowid
                    log.info("A new sprint successfully created with db id: {0}, sprint sprint id: {1}".format(id_value, id))
                else:
                    #TODO refactor this
                    cur.execute("UPDATE sprint  set name=?, sequence=?, state=?, goal=?, start_date=?, end_date=?, complete_date=? WHERE sprint_id=?",
                    (sprint_dict["name"], sprint_dict["sequence"], sprint_dict["state"], sprint_dict["goal"],sprint_dict["startDate"],sprint_dict["endDate"], sprint_dict["completeDate"],sprint_dict["id"],))
                    DB_CONNECTION.commit()
                                        
                    cur.execute("Select id from sprint where sprint_id = ?", (sprint_dict["id"],))
                    rows = cur.fetchall()
                    id_value = rows[0][0]
                    log.info("An updated sprint successfully for sprint db id: {0} with sprintid: {1}".format(id_value,sprint_dict["id"], ))
            else:
                log.error("unable to store sprint :{0}".format(sprint_dict))
                id_value = ""
            sprint_db_ids.append(str(id_value))
        except Exception as e:
            log.error("Exception unable to store sprint data{0} error received: {1}".format(sprint_dict, e))

    return sprint_db_ids


def multithread_collect_data():
    """
        Description: prepare multithread queues based on extracted versions and limited by number of threads specified on top of the file
    """

    global workQueue
    
    TH_JIRA_CONNECTION = connect_to_jira()
    number_of_threads = NUMBER_OF_THREADS
    workQueue = Queue()
    processes = []
    
    #create jobs and add them to the queue (for selected versions)
    if (TH_JIRA_CONNECTION != None):
        # populate a dictionary with all versions of the projects defined in the manifest.json file
        for project in MANIFEST_JSON["extract_for"]:
            # get project code and special filter, used
            _project_code = MANIFEST_JSON["extract_for"][project]["settings"]["project_code"]
            _special_filters = MANIFEST_JSON["extract_for"][project]["settings"]["special_filters"]


            # populate an dictonary with versions for all each project, and assign it to project version dicte
            version_dict[project] = get_project_versions(TH_JIRA_CONNECTION,
                                        _project_code[0],
                                        MANIFEST_JSON["extract_for"][project]["settings"]["regex_version"])
            log.info("Finish collecting versions for project: {0}".format(project))
            print("### Finish Versions for project: {0} ###".format(project))
            
            #create a new queue for each version so that each project and each version is analyzed by a different thread
            for version_name in version_dict[project]["version_name"]:
                version = {}
                version["version_name"] = version_name
                version["project_code"] = _project_code
                version["manifest_project_name"] = project
                version["special_filters"] = _special_filters
                workQueue.put(version)
                log.info("Finish adding version data to work queue: {0}".format(version))
                # version output: {'version_id': '1', 'project_code': ['project_code'], 'manifest_project_name': 'Project name', 'special_filters': ['issuetype in standardIssueTypes()']}

        log.debug("version dict:{0}".format(version_dict))
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
    """
        Description: each thread will extract and process the data for the version added in the queue
    """
    
    TH_JIRA_CONNECTION = connect_to_jira()
    
    # extract issues under populated versions
    if (TH_JIRA_CONNECTION is not None):
        while True:
            try:
                data = _work_queue.get_nowait()
                project_code = data["manifest_project_name"]
                collect_version_issues(TH_JIRA_CONNECTION, data["project_code"], data["special_filters"], data['version_name'])
                
            except queue.Empty:
                break

        return True


def populate_db():
    """
        Description: main function
    """

    global log

    log = logging.getLogger(__name__)
    
    if not os.path.exists('logs'):
        os.makedirs('logs')

    logging.basicConfig(filename='logs/log_data.log',level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    get_credentials()
    connect_to_db()
    multithread_collect_data()
    disconnect_from_db()


if __name__ == "__main__":
    print("### START from SRC ###")
    populate_db()
    print("###  DONE from SRC ###")