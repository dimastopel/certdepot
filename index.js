const express = require('express')
const exec = require('child_process').exec
const uuid = require('uuid/v4')
const bodyParser = require('body-parser')
const compression = require('compression')
const fs = require('fs')

const app = express()

const certPath = __dirname + "/certs/"; 
const counterFileName = certPath + "counter.txt";

app.use(express.static('static'))
app.use(bodyParser.urlencoded({ extended: false }))
app.use(compression())

app.post('/api/create', function (req, res) {

  var cn = req.body.cn
  var days = req.body.days
  var country = req.body.country
  var state = req.body.state
  var city = req.body.city
  var org = req.body.org
  var orgUnit = req.body.orgUnit
  var email = req.body.email
  var pfxPass = req.body.pfxPass

  if (!cn || cn === "")
  {
    console.log("Error: CN is empty. Doing nothing.")
    res.status(400).send({error: "Common Name can not be empty"})
    return;
  }

  var id = uuid();
  var names = getCertNames(id);

  var command = "openssl genrsa -out " + names.private + " 1024";  
  exec(command, 
    function (error, stdout, stderr) {
      if (error !== null) {
        console.log('exec error: ' + error);
        res.status(500).send({error: 'Failed to generate private key: ' + error});
        return;
      }

      var subj = "/commonName=" + cn;
      if (country && country != "") {
        subj += "/C=" + country;
      }
      if (state && state != "") {
        subj += "/ST=" + state;
      }
      if (city && city != "") {
        subj += "/L=" + city;
      }
      if (org && org != "") {
        subj += "/O=" + org;
      }
      if (orgUnit && orgUnit != "") {
        subj += "/OU=" + orgUnit;
      }
      if (email && email != "") {
        subj += "/emailAddress=" + email;
      }

      console.log("subj: " + subj);

      command = "openssl req -x509 -new -batch -subj " + escapeShell(subj) + " -key " + names.private + " -out " + names.public + " -days " + escapeShell(days);  
      exec(command, 
        function (error, stdout, stderr) {
          if (error !== null) {
            console.log('exec error: ' + error);
            res.status(500).send({error: 'Failed to generate public certificate: ' + error});
            return;
          }

          if (!pfxPass || pfxPass === "") {
            pfxPass = "password";
          }

          command = "openssl pkcs12 -export -inkey " + names.private + " -out " + names.pfx + " -in " + names.public + " -password pass:" + escapeShell(pfxPass);  
          exec(command, 
            function (error, stdout, stderr) {
              if (error !== null) {
                console.log('exec error: ' + error);
                res.status(500).send({error: 'Failed to create pfx: ' + error});
                return;
              }

              command = "bash createZip.sh " + names.zip_nodir + " " + names.private_nodir + " " + names.public_nodir;  
              exec(command, 
                function (error, stdout, stderr) {
                  if (error !== null) {
                    console.log('exec error: ' + error);
                    res.status(500).send({error: 'Failed to create ZIP archive: ' + error});
                    return;
                  }
                  console.log('Successfully generated certs for CN: ' + cn + ' ID:' + id);
                });
            });
        });
    });
  incCertCount()
  res.header('Content-Type', 'application/json');
  res.send({id:id});
});

app.get('/api/get/id/:certId/type/:certType', function(req, res) {
  var id = req.params.certId;
  var type = req.params.certType;
  var names = getCertNames(id);

  console.log('Retreiving certs for id: ' + id);


  if (type === "zip") {

    if (!fs.existsSync(names.zip)) {
      console.warn('can not find: ' + names.zip);
      res.status(404).send({error: 'Can not find cert for id/type: ' + id + "/" + type});
      return;
    }


    res.download(names.zip, names.zip, function(err) {
      if (err) {
        console.error('Can not return zip: ' + err);
      }
    });

  } else if (type === "pfx") {

    res.download(names.pfx, names.pfx, function(err) {
      if (err) {
        console.error('Can not return pfx: ' + err);
      }
    });

  } else {
    console.warn('Invalid type was sent: ' + type);
    res.status(400).send({error: 'Can not return cert for this type: ' + type});
  }
});

app.get('/api/count', function(req, res) {

  console.log('Retreiving certs count');

  var count = fs.readFileSync(counterFileName, 'utf8');

  res.send({"count":count});
});

function getCertNames(id) {
  var prefix = certPath + id + ".";
  var names = {};

  names.private = prefix + "private.pem";
  names.public = prefix + "public.pem";
  names.private_nodir = id + "." + "private.pem";
  names.public_nodir = id + "." + "public.pem";
  names.pfx = prefix + "pfx";
  names.zip = prefix + "private_public.zip";
  names.pfx_nodir = id + "." + "pfx";
  names.zip_nodir = id + "." + "private_public.zip";

  return names;
}

function escapeShell(cmd) {
  return '"'+cmd.replace(/(["\s'$`\\])/g,'\\$1')+'"';
};

function incCertCount() {

  if (fs.existsSync(counterFileName)) {
    var countString = fs.readFileSync(counterFileName);
    var count = parseInt(countString, 10)
    if (count != NaN)
    {
      fs.writeFileSync(counterFileName, (count+1).toString())
    }
  }
  else
  {
    fs.writeFileSync(counterFileName, "0")
  }
}

var port = process.env.NODE_PORT || 3000;
app.listen(port, function() {
  console.log('Example app listening on port ' + port)
})
