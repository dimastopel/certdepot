var express = require('express');
var app = module.exports = express.createServer();
//app.mongoose = require('mongoose');

app.mongoose = null;
var config = require('./config.js')(app, express);

var models = {};
//models.examples = require('./models/example')(app.mongoose);

require('./routes')(app, models, app.mongoose);

app.listen(process.env.PORT || 3000);