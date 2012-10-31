var exec = require('child_process').exec;
var uuid = require('node-uuid');
var fs = require('fs');

module.exports = function(app, models, mongoose){

  var title = "Certificate Depot"
  var description = "Create your self-signed SSL certificate instantly and free."

  /**
   *  Index
   */
  app.get('/', function(req, res){

    //get all the examples
    //models.examples.find({}, function(err, docs){
      
      //render the index page
      res.render('index.jade', {
          locals: {
            title: title,
            description: description,
            page: 'index'
          }
      });

    });
  //});
  
  /**
   *  Help
   */
  app.get('/help', function(req, res){
    //render the index page
    res.render('help.jade', {
        locals: {
          title: title,
          description: description,
          page: 'help'
        }
    });
  });


  function getCertNames(id)
  {
    var prefix = "/home/dima/certs/" + id + ".";
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


  /**
   *  Feedback
   */
  app.post('/feedback', function(req, res, next) {
    var feedback = req.body.feedback; 
    var connAddr = req.connection.remoteAddress
    var sockAddr = req.socket.remoteAddress

    var msg = connAddr + ' ' + sockAddr + ' ' + feedback + '\n';
    console.log('feedback: ' + msg);

    /*
    fs.open('feedback/feedback.txt', 'a', 666, function( e, id ) {
      fs.write( id, msg, undefined, undefined, undefined, function(){
        fs.close(id, function(){
          console.log('file closed, ip: ' + req.ip);
        });
      });
    });
    */

    var ws = fs.createWriteStream('feedback/feedback.txt', {flags: 'a', encoding: 'utf-8', mode: 0666 });
    ws.end(msg);

    res.send('Thanks!');
  });


  /**
   *  Create cert
   */
  app.post('/create', function(req, res, next) {
    //create the cert for a given id
    var cn = req.body.cn; //
    var days = req.body.days; //
    var country = req.body.country;
    var state = req.body.state;
    var city = req.body.city;
    var org = req.body.org;
    var orgUnit = req.body.orgUnit;
    var email = req.body.email;
    var pfxPass = req.body.pfxPass; //

    // get other cert info
    if (!cn || cn === "")
    {
      console.log("Error: CN is empty. Doing nothing.");
      res.send(400, {error: "Common Name can't be empty"});
      return;
    }

    //var prefix = "~/certs/" + encodeURIComponent(cn) + "--" + id + "--";
    //var privateCertName = prefix + "private.pem";
    //var publicCertName = prefix + "public.pem";
    //var pfxCertName = prefix + "pfx.pfx";
    var id = uuid.v4();
    var names = getCertNames(id);

    /*
    var opts = { encoding: 'utf8',
                 timeout: 0,
                 maxBuffer: 200*1024,
                 killSignal: 'SIGTERM',
                 cwd: "d:\\Utils\\OpenSSL-Win32\\bin\\",
                 env: null };
    */
    
    var command = "openssl genrsa -out " + names.private + " 1024";  
    exec(command, 
      function (error, stdout, stderr) {
        if (error !== null) {
          console.log('exec error: ' + error);
          res.send(500, {error: 'Failed to generate private key: ' + error});
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

        command = "openssl req -x509 -new -batch -subj \"" + subj + "\" -key " + names.private + " -out " + names.public + " -days " + days;  
        exec(command, 
          function (error, stdout, stderr) {
            if (error !== null) {
              console.log('exec error: ' + error);
              res.send(500, {error: 'Failed to generate public certificate: ' + error});
              return;
            }

            if (!pfxPass || pfxPass === "") {
              pfxPass = "password";
            }

            command = "openssl pkcs12 -export -inkey " + names.private + " -out " + names.pfx + " -in " + names.public + " -password pass:" + pfxPass;  
            exec(command, 
              function (error, stdout, stderr) {
                if (error !== null) {
                  console.log('exec error: ' + error);
                  res.send(500, {error: 'Failed to create pfx: ' + error});
                  return;
                }

                command = "bash ~/github/certdepot/createZip.sh " + names.zip_nodir + " " + names.private_nodir + " " + names.public_nodir;  
                exec(command, 
                  function (error, stdout, stderr) {
                    if (error !== null) {
                      console.log('exec error: ' + error);
                      res.send(500, {error: 'Failed to create ZIP archive: ' + error});
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
  });

  app.get('/getcert/id/:certId/type/:certType', function(req, res, next) {
    var id = req.params.certId;
    var type = req.params.certType;
    var names = getCertNames(id);

    console.log(JSON.stringify(names));

    if (type === "zip") {

      if (!fs.existsSync(names.zip)) {
        console.warn('can not find: ' + names.zip);
        res.send(404, {error: 'Can not find cert for id/type: ' + id + "/" + type});
        return;
      }


      res.download(names.zip, names.zip, function(err) {
        if (err) {
          console.error('Can not return zip: ' + err);
        }
      });

    } else if (type === "pfx") {

      /*
      if (!fs.existsSync(names.pfx)) {
        console.warn('can not find: ' + names.pfx);
        res.send(404, {error: 'Can not find cert for id/type: ' + id + "/" + type});
        return;
      }
      */

      res.download(names.pfx, names.pfx, function(err) {
        if (err) {
          console.error('Can not return pfx: ' + err);
        }
      });

    } else {
      console.warn('Invalid type was sent: ' + type);
      res.send(400, {error: 'Can not return cert for this type: ' + type});
    }
  });





  /**
   *  Add test doc
   */
   /*
  app.post('/posts', function(req, res){
     var now = new Date();
     var Post = models.examples;
     var post = new Post();
     post.name = req.param('doc');
     post.date = now;
     post.save(function(err) {
         console.log('error check');
         if(err) { throw err; }
         console.log('saved');
     });
     res.redirect('/list');
  });
*/
  
};