#!/usr/bin/python
# coding: utf-8
import urllib2
import json
import calendar
import time
import locale
import subprocess
import shlex
import os
import traceback

UUID_FILE="uuid"
FLOWS_FILE="flows.json"
CONFIG_FILE="rmbt.cfg"
RMBT_BIN="rmbt"
#DEBUG printouts
DEBUG=True

class Settings:
    def __init__(self):
        self.language=locale.getdefaultlocale()[0];
        self.timezone=subprocess.Popen(shlex.split("date +%Z"),stdout=subprocess.PIPE).stdout.read()[:-1]

    def get_time(cls):
        return str(int(round(calendar.timegm(time.gmtime())*1000)))


def request_uuid(sets):
    """Creates a http request and ask the control server fo correct uuid"""
    #create json to request uuid
    req_json={
        "language": sets.language,
        "timezone": sets.timezone,
        "name": "RMBT",
        "terms_and_conditions_accepted": "true",
        "type": "DESKTOP",
        "version_code": "1",
        "version_name": "1.0",
    }

    #load uuid saved in file
    if os.path.isfile(UUID_FILE):
        with open(UUID_FILE,'r') as uuid_file:
            lines = uuid_file.read().split('\n')
            uuid_file.close()
            req_json['uuid']=lines[0];
    else:
        print('uuid file not found, requesting new one.')
        req_json['uuid']=0;

    #creating GET request to obtain / check uuid
    req = urllib2.Request('https://netmetr-control.labs.nic.cz/RMBTControlServer/settings')
    req.add_header('Accept', 'application/json, text/javascript, */*; q=0.01')
    req.add_header('Content-Type', 'application/json')
    if DEBUG:
        print('\033[93m'+"Test settings request:"+'\033[0m')
        print(json.dumps(req_json, indent=2))
    #send the request
    resp = urllib2.urlopen(req,json.dumps(req_json))
    resp_json=json.loads(resp.read());
    uuid_new=resp_json["settings"][0].get("uuid",'')
    if uuid_new!='': #new uuid was received
        sets.uuid=uuid_new;
        with open(UUID_FILE,"w") as uuid_file:
            uuid_file.write(sets.uuid)
            uuid_file.close()
    else:
        sets.uuid=req_json['uuid']
    if DEBUG:
        print('\033[93m'+"Test settings response:"+'\033[0m')
        print(json.dumps(resp_json, indent=2))


def request_settings(sets):
    """Creates a http request to get test token, number of threads, number
    of pings, server address and port and so on.
    """
    #create request to start a test
    req = urllib2.Request('https://netmetr-control.labs.nic.cz/RMBTControlServer/testRequest')
    #add headers
    req.add_header('Accept', 'application/json, text/javascript, */*; q=0.01')
    req.add_header('Content-Type', 'application/json')
    #create the json to send
    req_json={
        "client":"RMBT",
        "language":sets.language,
        "time": sets.get_time(),
        "timezone":sets.timezone,
        "type":"DESKTOP",
        "uuid":    sets.uuid,
        "version":"0.1",
        "version_code":"1"
    }
    if DEBUG:
        print('\033[93m'+"Test testRequest request"+'\033[0m');
        print(json.dumps(req_json, indent=2))

    #send the request
    resp = urllib2.urlopen(req,json.dumps(req_json))
    #read the content
    resp_json=json.loads(resp.read())

    if DEBUG:
        print('\033[93m'+"Test testRequest response:"+'\033[0m');
        print(json.dumps(resp_json, indent=2))

    sets.test_server_address=resp_json["test_server_address"]
    sets.test_server_port=resp_json["test_server_port"]
    sets.test_token=resp_json["test_token"]
    sets.test_uuid=resp_json["test_uuid"]
    sets.test_numthreads=resp_json["test_numthreads"]
    sets.test_numpings=resp_json["test_numpings"]
    sets.test_server_encryption=resp_json["test_server_encryption"]
    sets.test_duration=resp_json["test_duration"]


def measure_pings(sets):
    """Run serie of pings to the test server and computes & saves
     the lowest one
    """
    if DEBUG:
        print('\033[93m'+"Starting ping test..."+'\033[0m')
    ping_proc=subprocess.Popen(
        ["ping", sets.test_server_address,
         "-c", sets.test_numpings],stdout=subprocess.PIPE)
    ping_result_lines=ping_proc.stdout.read().split('\n')
    ping_values=list()
    for i in range(1,int(sets.test_numpings)+1):
        try:
            start = ping_result_lines[i].index("time=") + len("time=")
            end = ping_result_lines[i].index(" ms" )
            ping=int(float(ping_result_lines[i][start:end])*1000000)
            ping_values.append(ping)
        except:
            print("Problem decoding pings.")
            return ''
    return min(int(s) for s in ping_values)


def measure_speed(sets):
    """Start RMBT client with saved arguments to measure the speed
    """
    #Create config file needed by rmbt-client
    if os.path.isfile(CONFIG_FILE):
        try:
            os.remove(CONFIG_FILE)
        except:
            traceback.print_exc()
            return ''

    try:
        with open(CONFIG_FILE,"w") as config_file:
            config_file.write("{\"cnf_file_flows\": \""+FLOWS_FILE+".xz\"}");
            config_file.close()
    except:
        print("Error creating config file")
        traceback.print_exc()
        return ''

    encryption={True:"-e"}
    if DEBUG:
        print('\033[93m'+"Starting speed test..."+'\033[0m')
    test_proc=subprocess.Popen(
        shlex.split(RMBT_BIN+" "+encryption.get(sets.test_server_encryption,"")+ " -h "+
            sets.test_server_address+ " -p "+ str(sets.test_server_port)+" -t "+
            sets.test_token+" -f "+sets.test_numthreads+ " -d "+
            sets.test_duration+ " -u "+ sets.test_duration + " -c " +
            CONFIG_FILE),
        stdout=subprocess.PIPE)
    test_result=test_proc.stdout.read()
    if DEBUG:
        print('\033[93m'+"Speed test result:"+'\033[0m')
        print(test_result)
    return json.loads(test_result.split("}")[1] + "}")


def import_speed_flows(speed_array):
    """The speedtest flow is saved to a file during the test. This function
    imports it so it could be sent to the control server.
    """
    if os.path.isfile(FLOWS_FILE):
        try:
            os.remove(FLOWS_FILE)
        except:
            traceback.print_exc()
            return

    directions={
        "dl":"download",
        "ul":"upload"
    }
    try:
        subprocess.call(shlex.split("unxz "+FLOWS_FILE+".xz"))
        with open(FLOWS_FILE,'r') as json_data:
            flows_json=json.load(json_data)
            json_data.close()
    except:
        print('Problem reading/decoding flows data.')
        traceback.print_exc()
        return

    for direct, direction in directions.iteritems():
        thread = 0;
        #each direction has multiple threads
        for flow in flows_json["res_details"][direct]:
            last_time = 0
            #each thread has plenty of samples - we want to use a small amount of them
            for sample in flow["time_series"]:
                if (sample.get("t")-last_time)>30000000:
                    last_time=sample["t"]
                    speed_array.append({
                        "direction": direction,
                        "thread":thread,
                        "time":sample["t"],
                        "bytes":sample["b"]
                     })
            thread+=1


    #Remove generated files
    try:
        os.remove(FLOWS_FILE)
    except:
        traceback.print_exc()
    try:
        os.remove(CONFIG_FILE)
    except:
        traceback.print_exc()


def upload_result(sets,pres,test_result_json,speed_array):
    """Uploads the tests result to the control server.
    """
    req_json={
        "client_language": sets.language,
        "client_name": "RMBT",
        "client_uuid": sets.uuid,
        "client_version": "0.1",
        "client_software_version": "0.3",
        "geoLocations": [],
        "model": "Turris",
        "network_type": 98,
        "platform": "RMBT",
        "product": "(user agent)",   #TODO
        "test_bytes_download": test_result_json.get("res_total_bytes_dl",{}),
        "test_bytes_upload": test_result_json.get("res_total_bytes_ul",{}),
        "test_nsec_download": test_result_json.get("res_dl_time_ns",{}),
        "test_nsec_upload": test_result_json.get("res_ul_time_ns",{}),
        "test_num_threads": test_result_json.get("res_dl_num_flows",{}),
        "test_ping_shortest" : pres,
        "num_threads_ul": test_result_json.get("res_ul_num_flows",{}),
        "test_speed_download": test_result_json.get("res_dl_throughput_kbps",{}),
        "test_speed_upload": test_result_json.get("res_ul_throughput_kbps",{}),
        "test_token": sets.test_token,
        "test_uuid": sets.test_uuid,
        "timezone": sets.timezone,
        "type": "DESKTOP",
        "version_code": "1",
        "developer_code": 0
    }
    if DEBUG:
        print('\033[93m'+"Save result request (without speed array and pings):"+'\033[0m');
        print(json.dumps(req_json, indent=2))

    req_json["speed_detail"]=speed_array
    req_json["pings"]=[]

    #create GET request
    req = urllib2.Request('https://netmetr-control.labs.nic.cz/RMBTControlServer/result')
    #add headers
    req.add_header('Accept', 'application/json, text/javascript, */*; q=0.01')
    req.add_header('Content-Type', 'application/json')
    #send the request
    resp = urllib2.urlopen(req,json.dumps(req_json))
    resp_json=json.loads(resp.read());
    if DEBUG:
        print('\033[93m'+"Save result response:"+'\033[0m');
        print(json.dumps(resp_json, indent=2))


settings=Settings()
request_uuid(settings)
request_settings(settings)

shortest_ping=measure_pings(settings)
speed_result=measure_speed(settings)
if speed_result=='':
    quit()

speed_flows=list()
import_speed_flows(speed_flows)

upload_result(settings,shortest_ping,speed_result,speed_flows)
