import requests
import sys

if __name__ == "__main__":
    file_path = sys.argv[1]
    upload_file = open(file_path,mode='rb')
    data = requests.post('https://cdn-ms.juejin.im/v1/upload?bucket=gold-user-assets',files={'file': upload_file}).json()
    print('upload url: ' + data['d']['url']['https'])
    