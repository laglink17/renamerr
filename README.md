# Renamerr

This is a Web Service Program that connects to **Sonarr**, gets current indexed Series and lets you choose an **Alternative Name** (from Sonarr list) to rename the files using this chosen Name.

Focused on Anime Series, that most of the times gets a Translated Name from Sonarr.

# First Steps

 1. Clone or download this repository and added to your Docker server.
 2. User Dockerfile to create an image for the service
     `sudo docker build -t renamerr .`
 3.  Create the docker services, using the docker-compose file.
     `sudo docker compose up`
 4. Access the service with http://{server-ip}:5000

## Usage

Select a Series from the list, and get the Alternative Names from Sonarr. Choose your prefered Alternative Name and press "Preview Rename" to see how the files will be renamed.

Press the botom "Confirm Rename" to rename the files.

Enjoy!# renamerr
Web Service Program to rename Anime Series from Sonarr
