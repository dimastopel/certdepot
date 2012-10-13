var exec = require('child_process').exec;
var uuid = require('node-uuid');

module.exports = function(app, models, mongoose){

  var title = "Certificate Depot"
  var description = "Create your self-signed certificate instantly and free."

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
   *  Fill info
   */
  app.post('/fillinfo', function(req, res){
    //render the index page
    res.render('fillinfo.jade', {
        locals: {
          title: title,
          description: description,
          common_name: req.param('cn'),
          page: 'fillinfo'
        }
    });
  });

  /**
   *  Download
   */
  app.post('/download', function(req, res){

    // create certs here
    var country = req.param("country");
    var state = req.param("state");
    var city = req.param("city");
    var org = req.param("org");
    var org_unit = req.param("org_unit");
    var cn = req.param("cn");
    var email = req.param("email");

    if (cn === "")
    {
      console.log("Error: CN is empty. Doing nothing.");
      return;
    }


    var id = uuid.v4();
    console.log("uuid: " + id);

    var prefix = "~/certs/" + cn + "--" + id + "--";

    var opts = { encoding: 'utf8',
                 timeout: 0,
                 maxBuffer: 200*1024,
                 killSignal: 'SIGTERM',
                 cwd: "d:\\Utils\\OpenSSL-Win32\\bin\\",
                 env: null };

    
    var command = "openssl genrsa -out " + prefix + "private.txt 1024";  
    exec(command, 
      function (error, stdout, stderr) {
        console.log('stdout: ' + stdout);
        console.log('stderr: ' + stderr);
        if (error !== null) {
          console.log('exec error: ' + error);
          return;
        }
      
        console.log("generating public cert");
        command = "openssl req -x509 -new -batch -subj \"/commonName=" + cn + "\" -key " + prefix + "private.txt " + " -out " + prefix + "public.txt";  
        console.log(command);
        exec(command, 
          function (error, stdout, stderr) {
            console.log('stdout: ' + stdout);
            console.log('stderr: ' + stderr);
            if (error !== null) {
              console.log('exec error: ' + error);
            }
          }
        );
      }
    );
    


    // FINISHED HERE !!! CAN'T CRATE PUBLIC CERT. NEED TO PROVIDE CN VIA COMMAND LINE. 

    // end


    //render the index page
    res.render('download.jade', {
        locals: {
          title: title,
          description: description,
          page: 'download'
        }
    });
  });

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

  /**
   *  Create cert
   */
  app.post('/create/id/:certid/type/:certtype', function(req, res, next){
    //create the cert for a given id
    var id = req.params.certid;
    var type = req.params.certtype;
    var cn = req.body.cn;

    // get other cert info
    console.log("body: " + JSON.stringify(req.body));
    if (!cn || cn === "")
    {
      console.log("Error: CN is empty. Doing nothing.");
      res.send(400, {error: "Common Name can't be empty"});
      return;
    }


    console.log("id: " + id + ", cn: " + cn);

    var prefix = "~/certs/" + encodeURIComponent(cn) + "--" + id + "--";

    /*
    var opts = { encoding: 'utf8',
                 timeout: 0,
                 maxBuffer: 200*1024,
                 killSignal: 'SIGTERM',
                 cwd: "d:\\Utils\\OpenSSL-Win32\\bin\\",
                 env: null };
    */
    
    var command = "openssl genrsa -out " + prefix + "private.txt 1024";  
    exec(command, 
      function (error, stdout, stderr) {
        console.log('stdout: ' + stdout);
        console.log('stderr: ' + stderr);
        if (error !== null) {
          console.log('exec error: ' + error);
          res.send(500, {error: 'Failed to generate private key: ' + error});
          return;
        }
      
        console.log("generating public cert");
        command = "openssl req -x509 -new -batch -subj \"/commonName=" + cn + "\" -key " + prefix + "private.txt " + " -out " + prefix + "public.txt";  
        console.log(command);
        exec(command, 
          function (error, stdout, stderr) {
            console.log('stdout: ' + stdout);
            console.log('stderr: ' + stderr);
            if (error !== null) {
              console.log('exec error: ' + error);
              res.send(500, {error: 'Failed to generate public certificate: ' + error});
              return;
            }
          }
        );
      }
    );

    res.send('Successfully created certificate for id: ' + id);
  });


  /**
   *  Add View
   */
  app.get('/add', function(req, res){

      //render the add page
      res.render('add.jade', {
          locals: {
            title: 'Node.js Express MVR Template',
            page: 'add'
          }
      });
  });
  
  /**
   *  Add test doc
   */
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
  
};