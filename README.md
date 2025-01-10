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

![renamerr_preview_v2](https://github.com/user-attachments/assets/f48d162c-20ba-4cb0-98eb-8c41ae97b18a)

Choose your prefered Alternative Name and if you prefer to use Season Folders or a Single Folder, the press "Preview Rename" to see how the files will be renamed.

Season Folder:

![renamerr_season](https://github.com/user-attachments/assets/7cf29e17-a66d-4286-b24d-23265e754132)

Single Folder:

![renamerr_single](https://github.com/user-attachments/assets/40d67dc2-5755-4cfd-abcd-35cf28ba3471)

Press the botom "Confirm Rename" to rename the files.

Enjoy!

## Warnings

 - Sonarr and Renamerr **must have** the same path for the file. In the compose file, both are registered on /anime.
 - Create the enviroment variables for UID, GID and API. 
 - It's recommend to first create and configure Sonarr, before using this service. The API is needed to access Sonarr files.
