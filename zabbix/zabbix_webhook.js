try {
    Zabbix.Log(4, 'vfzsync script value=' + value);

    var result = {
        'tags': {
            'endpoint': 'vfzsync'
        }
    },
        params = JSON.parse(value),
        req = new CurlHttpRequest(),
        fields = {},
        resp;

    req.AddHeader('Content-Type: application/json');
    // {"host" : "Host", "tags": "tags", "status": 1 }
    message = JSON.parse(params.message);
    Zabbix.Log(4, 'vfzsync message : ' + JSON.stringify(message));
    host = message.host;
    key = message.tags;
    status = message.status;
    url = params.url + '?async&mode=' + params.mode + '&host=' + host + '&key=' + key + '&status=' + status;
    Zabbix.Log(4, 'vfzsync url : ' + url);
    resp = req.Get(url);
    
    if (req.Status() != 200) {
        throw 'Response code: ' + req.Status();
    }

    resp = JSON.parse(resp);

} catch (error) {
    Zabbix.Log(4, 'vfzsync action failed json : ' + JSON.stringify(params));
    Zabbix.Log(4, 'vfzsync action failed : ' + error);

    result = {};
}

return JSON.stringify(result);