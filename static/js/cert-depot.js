

function createCert()
{

  var form = document.querySelector("#cert-form");
  var data = serialize(form);

  var xmlHttp = new XMLHttpRequest();
  xmlHttp.onreadystatechange = function() { 
      if (xmlHttp.readyState === 4)
      {
        if (xmlHttp.status === 200)
        {
          handleSuccess(xmlHttp.responseText);
        }
        else
        {
          handleError(xmlHttp.statusText);
        }
      }
  }
  xmlHttp.open("POST", "/api/create", true); // true for asynchronous 
  xmlHttp.setRequestHeader("Content-type", "application/x-www-form-urlencoded");
  xmlHttp.send(data);


}

function handleSuccess(response_data)
{
  document.getElementById("status-message").classList.add("success-status-message");
  document.getElementById("status-message").style.visibility = "visible";
  document.getElementById("download-buttons").style.visibility = "visible";

  var response = JSON.parse(response_data);

  document.getElementById("download-pfx").href = "/api/get/id/" + response.id + "/type/pfx";
  document.getElementById("download-pem").href = "/api/get/id/" + response.id + "/type/zip";
}

function handleError(response_data)
{
  //var response = JSON.parse(response_data);

  document.getElementById("status-message").classList.add("error-status-message");
  document.getElementById("status-message").style.visibility = "visible";
  document.getElementById("status-message-text").innerHTML = "Server side error occured: '" + response_data + "'";
}

function httpGet(theUrl)
{
    var xmlHttp = new XMLHttpRequest();
    xmlHttp.open( "GET", theUrl, false ); // false for synchronous request
    xmlHttp.send( null );
    return xmlHttp.responseText;
}

function httpGetAsync(theUrl, callback)
{
    var xmlHttp = new XMLHttpRequest();
    xmlHttp.onreadystatechange = function() { 
        if (xmlHttp.readyState == 4 && xmlHttp.status == 200)
            callback(xmlHttp.responseText);
    }
    xmlHttp.open("GET", theUrl, true); // true for asynchronous 
    xmlHttp.send(null);
}


function foo()
{
  httpGetAsync("/api/rand", fillTable);
}

function fillTable(dataString)
{
  var table = document.getElementById("demo-table");
  while ( table.rows.length > 0 )
  {
    table.deleteRow(0);
  }

  var data = JSON.parse(dataString);
  for (var prop in data) {
      if (data.hasOwnProperty(prop)) {
        // Create an empty <tr> element and add it to the 1st position of the table:
        var row = table.insertRow(0);

        // Insert new cells (<td> elements) at the 1st and 2nd position of the "new" <tr> element:
        var cell1 = row.insertCell(0);
        var cell2 = row.insertCell(1);

        // Add some text to the new cells:
        cell1.innerText = prop;
        cell2.innerText = data[prop];
      }
  }
}

// Modal

document.addEventListener("DOMContentLoaded", function(event) { 

  var modal = document.querySelector('.modal');
  var closeButtons = document.querySelectorAll('.close-modal');
  // set open modal behaviour
  document.querySelector('.open-modal').addEventListener('click', function() {
    modal.classList.toggle('modal-open');
  });
  // set close modal behaviour
  for (i = 0; i < closeButtons.length; ++i) {
    closeButtons[i].addEventListener('click', function() {
      modal.classList.toggle('modal-open');
    });
  }
  // close modal if clicked outside content area
  document.querySelector('.modal-inner').addEventListener('click', function() {
    modal.classList.toggle('modal-open');
  });
  // prevent modal inner from closing parent when clicked
  document.querySelector('.modal-content').addEventListener('click', function(e) {
    e.stopPropagation();
  });

});





