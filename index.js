//index.js
const express = require('express')
const exec = require('child_process').exec
const uuid = require('uuid/v4')
const bodyParser = require('body-parser')
const fs = require('fs')

const app = express()

const certPath = __dirname + "/certs/"; 

app.use(express.static('static'))
app.use(bodyParser.urlencoded({ extended: false }))

app.post('/api/create', function (req, res, next) {
    
    var cn = req.body.cn
    var days = req.body.days
    var country = req.body.country
    var state = req.body.state
    var city = req.body.city
    var org = req.body.org
    var orgUnit = req.body.orgUnit
    var email = req.body.email
    var pfxPass = req.body.pfxPass

    // get other cert info
    if (!cn || cn === "")
    {
      console.log("Error: CN is empty. Doing nothing.")
      res.status(400).send({error: "Common Name can't be empty"})
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
                  }
                  );
              }
              );
          }
          );
      }
      );

    res.header('Content-Type', 'application/json');
    res.send({id:id});
  })

app.listen(3000, function() {
  console.log('Example app listening on port 3000!')
})




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