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

Select a Series from the list, and get the Alternative Names from Sonarr. 

![Renamerr_select](https://github.com/user-attachments/assets/fd291434-1656-4418-8c0f-185580e5f882)

Choose your prefered Alternative Name and press "Preview Rename" to see how the files will be renamed.

![renamerr_preview](https://github.com/user-attachments/assets/e425e786-a7ab-4e38-9697-ef4b8a95536b)

Press the botom "Confirm Rename" to rename the files.

Enjoy!

## Warnings

 - Sonarr and Renamerr **must have** the same path for the file. In the compose file, both are registered on /anime.
 - Create the enviroment variables for UID, GID and API. 
 - It's recommend to first create and configure Sonarr, before using this service. The API is needed to access Sonarr files.
