
function showStatus(success, message) {
  var status = document.getElementById("status-message");

  if (success && !status.classList.contains("success-status-message")) {
    status.classList.remove("error-status-message")
    status.classList.add("success-status-message");
  }

  if (!success && !status.classList.contains("error-status-message")){
    status.classList.remove("success-status-message")
    status.classList.add("error-status-message");
  }

  //status.style.visibility = "visible";
  status.innerHTML = (success ? "SUCCESS: " : "ERROR: ") + message;
}
function createCert()
{

  var form = document.querySelector("#cert-form");
  var data = serialize(form);

  if (!form.checkValidity || form.checkValidity()) {
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
  } else {
    showStatus(false, "Please make sure all form fields are valid");
  }
}

function handleSuccess(response_data)
{
  var response = JSON.parse(response_data);

  showStatus(true, "Please download the certificate using one of the buttons below. [CertId: " + response.id.substring(0,8) + "...]");
  document.getElementById("download-buttons").style.visibility = "visible";

  document.getElementById("download-pfx").href = "/api/get/id/" + response.id + "/type/pfx";
  document.getElementById("download-pem").href = "/api/get/id/" + response.id + "/type/zip";
}

function handleError(response_data)
{
  //var response = JSON.parse(response_data);
  showStatus(false, "Server side error occured: '" + response_data + "'");
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





