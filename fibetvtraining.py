import subprocess
import os
import pyodbc
import paramiko
from sqlalchemy import create_engine
import pandas as pd
import zipfile
import datetime



# Database connection details
server = 'CPCDWD-4033.belldev.dev.bce.ca'
database = 'FIBE_TV'
username = 'Analanceetl'
password = 'Sry@sbrs1uat'

try:

    conn_str = f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server};DATABASE={database};UID={username};PWD={password}'

# Create a connection using pyodbc
    connection = pyodbc.connect(conn_str)   
    engine = create_engine(f'mssql+pyodbc:///?odbc_connect={conn_str}') 
 
except pyodbc.DatabaseError as de:
    # If there is an issue specifically with the database
    print(f"DatabaseError: There was an issue with the database. Details: {de}")

# Path to your batch file
bat_file = r"E:\pythonforfibe\python_FIBE\Batch\Deletebatchfibe.bat"

# Run the batch file
process = subprocess.run(bat_file, shell=True,text=True)

# Create cursor
cursor = connection.cursor()
cursor.execute("Truncate table FTV_STG_PROD_inv_JS")
cursor.execute("Truncate table FTV_STG_PROD_ord_JS")
cursor.execute("Truncate table FTV_STG_RESOURCE_JS")


# SFTP connection details
sftp_host = "cpcdwa-4061.belldev.dev.bce.ca"
sftp_port = 22  # Default SFTP port
sftp_username = "cpm_etl_uat"
private_key_path = "E:/pythonforfibe/bala/MDM_PROD_PrivateKey_ssh.pem"

# Function to establish SFTP connection
def sftp_connect():
    sftp = None
    transport = None
    try:
        transport = paramiko.Transport((sftp_host, sftp_port))
        private_key = paramiko.RSAKey.from_private_key_file(private_key_path)
        transport.connect(username=sftp_username, pkey=private_key)
        sftp = paramiko.SFTPClient.from_transport(transport)
        print(f"Successfully connected to {sftp_host}")
        return sftp, transport

    
    except Exception as e:
        print(f"Failed to connect to {sftp_host}: {e}")


download_folder = 'E:/pythonforfibe/python_FIBE/files/input'
remote_path = '/CPM_NonProd/UAT1/cpm_brs/input/ProductInv'
remote_path_RES_order ='/CPM_NonProd/UAT1/cpm_brs/input'
remote_path_output="/CPM/dev/cpmbrs/output"
local_output_folder='E:/pythonforfibe/python_FIBE/files/output'
timestamp_f = datetime.datetime.now()
timestamp = timestamp_f.strftime('%Y%m%d_%H%M%S')
process_id=timestamp.replace('_','')
ETL_start_time=timestamp_f.strftime("%Y-%m-%d %H:%M:%S.") + str(timestamp_f.microsecond)[:3].rjust(3, '0')
sql_query = """Select Distinct R.subscriptionId "SubscriptionID", 
                    I.productStatus as "ProductStatus", 
                    externalProductId as "ExternalProductID", 
                    case when resourceSpecificationName in ('VideoWiredAdapterCpe_LD', 'VideoAccessPointCpe_LD') and acquisitionType='' then 'NA' 
                    else acquisitionType end as "AcquisitionType", 
                    resourceStatus as "ResourceStatus", 
                    resourceSpecificationName as "ResourceSpecificationName", 
                    equipmentType as "EquipmentType", 
                    modelType as "ModelType", 
                    modelNo as "Model#", 
                    serialNo as "Serial#", 
                    case when activationDate = 'NA' then '' 
                    else cast(format(cast(replace(replace(activationDate, 'T', ' '),'Z','') as datetime), 'yyyy-MM-dd HH:mm:ss') as varchar(100)) end as "ActivationDate", 
                    case when deactivationDate = 'NA' then '' 
                    else cast(format(cast(replace(replace(deactivationDate, 'T', ' '),'Z','') as datetime), 'yyyy-MM-dd HH:mm:ss') as varchar(100)) end as "DeactivationDate", 
                    hoi as "HOIID", 
                    cast(format(cast(replace(replace(R.loadTime, 'T', ' '),'Z','') as datetime), 'yyyy-MM-dd HH:mm:ss') as varchar(100)) as "LastUpdatedDate"
                From FTV_RESOURCE_DELTA R
                Left Join FTV_PROD_ORD_DELTA O
                On R.subscriptionId = O.subscriptionId
                And Isnull(R.SourceName, '') not in ('TVSI')
                Left Join FTV_PROD_INV_ATTR I
                On R.subscriptionId = I.subscriptionId
                And R.externalProductId = I.productExternalId
                where resourceSpecificationName <> 'NpacSubscription_LDA'"""

# Function to get the files to download based on patterns
def get_files_to_download(sftp, remote_path):
                                            
    remote_files = sftp.listdir(remote_path)
    
                                                       
    patterns = ['ProductInvArchive', 'ProductInvInFlight', 'ProductInvLive']  # Default patterns

    
                                        
    files_to_download = [file for file in remote_files if any(pattern in file for pattern in patterns)]
    
    return files_to_download

def get_files_to_download_res_prod(sftp, remote_path_RES_order):
    
    remote_file_res_order=sftp.listdir(remote_path_RES_order)

    res_pattern=['CPM_EDW_Resource','ProductOrder']

    files_to_download_res = [file for file in remote_file_res_order if any(pattern in file for pattern in res_pattern)]
    
    return files_to_download_res

# Function to download files from SFTP to the local machine
def download_files(sftp, download_folder, remote_path,remote_path_RES_order):
          
    files_to_download = get_files_to_download(sftp, remote_path)

    for file in files_to_download:
        try:
            remote_file = os.path.join(remote_path, file)
            
            local_file = os.path.join(download_folder, file)
            sftp.get(remote_file, local_file)
            
            print(f"Downloaded: {file}")
            process_and_insert_data(file, local_file,connection,cursor)
    
        except FileNotFoundError:
            print(f"File not found: {file}")
        except Exception as e:
            print(f"Error downloading {file}: {str(e)}")

    files_to_download_res=get_files_to_download_res_prod(sftp, remote_path_RES_order)

    for file in files_to_download_res:
        try:
            remote_file = os.path.join(remote_path_RES_order, file)
            
            local_file = os.path.join(download_folder, file)
            sftp.get(remote_file, local_file)
            
            print(f"Downloaded: {file}")
            process_and_insert_data(file, local_file,connection,cursor)
    
        except FileNotFoundError:
            print(f"File not found: {file}")
        except Exception as e:
            print(f"Error downloading {file}: {str(e)}")



def process_and_insert_data(file_name, local_file, connection, cursor):
    try:
         with open(local_file, 'r', newline='') as file:
            file_contents = file.read()
        
        # Replace LF with CRLF
         modified_contents = file_contents.replace('\n', '\r\n')

        # Write the modified contents back to the file
         with open(local_file, 'w', newline='') as file:
            file.write(modified_contents)

         table_name = None
         flow = None
         if 'ProductInvArchive' in file_name:
             table_name = 'FTV_STG_PROD_inv_JS'
             flow = 'Archive'
             sql_query = """EXEC sp_bulk_insert_archive_Inflight_Live 
    @Flow = ?, 
    @TableName = ?, 
    @FilePath = ?;"""
             print(f"Executing query: {sql_query}")
             cursor.execute(sql_query, (flow, table_name, local_file))
             connection.commit()

         elif 'ProductInvInFlight' in file_name:
             table_name = 'FTV_STG_PROD_inv_JS'
             flow = 'Inflight'
             sql_query = """EXEC sp_bulk_insert_archive_Inflight_Live 
    @Flow = ?, 
    @TableName = ?, 
    @FilePath = ?;"""
             print(f"Executing query: {sql_query}")
             cursor.execute(sql_query, (flow, table_name, local_file))
             connection.commit()

         elif 'ProductInvLive' in file_name:
             table_name = 'FTV_STG_PROD_inv_JS'
             flow = 'Live'
             sql_query = """EXEC sp_bulk_insert_archive_Inflight_Live 
    @Flow = ?, 
    @TableName = ?, 
    @FilePath = ?;"""
             print(f"Executing query: {sql_query}")
             cursor.execute(sql_query, (flow, table_name, local_file))
             connection.commit()

         elif 'ProductOrder' in file_name:
             table_name = 'FTV_STG_PROD_ord_JS'
             sql_query = """exec sp_bulk_insert_RESOURCE_ord
     @TableName = ?, 
     @FilePath = ?;"""
             print(f"Executing query: {sql_query}")
             cursor.execute(sql_query, (table_name, local_file))
             connection.commit()

         elif 'CPM_EDW_Resource' in file_name:
             table_name = 'FTV_STG_RESOURCE_JS'
             sql_query = """exec sp_bulk_insert_RESOURCE_ord
     @TableName = ?, 
     @FilePath = ?;"""
             print(f"Executing query: {sql_query}")
             cursor.execute(sql_query, (table_name, local_file))
             connection.commit()

         else:
             print(f"Unknown file pattern: {file_name}. Skipping insertion.")
             return

    except Exception as e:
                    raise Exception(f"facing error while running this query{e}")

   

def temp_cleanup(cursor,connection):
    try:
       cursor.execute("Delete From FTV_STG_PROD_INV_JS Where Content='' or Content Like '%rows returned'")
       cursor.execute("Delete From FTV_STG_PROD_ORD_JS Where Content='' or Content Like '%rows returned'")
       cursor.execute("Delete From FTV_STG_RESOURCE_JS Where Content='' or Content Like '%rows returned'")
       print("temp_cleanup completed")
       connection.commit()
    except Exception as e:
        print("error while deleting table : {e}")

def delta_and_attr_population(cursor,connection):
    try:
        cursor.execute("exec SP_PROD_RESC_DELTA_ATTR_LOAD")
        print("delta and update attr completed")
        connection.commit()


    except Exception as e:
        print("error while triggereing_sp : {e}")

def generate_csvfile(engine,timestamp,sql_query):

# Fetch data from the database into a DataFrame
    df = pd.read_sql(sql_query,engine)

# Define a valid file path for saving the CSV
    csv_file_path = f'E:/pythonforfibe/python_FIBE/files/output/CPM_EDW_HardwareInfo_{timestamp}.csv'  # Fixed the '|' issue by replacing it with '_'

# Write the DataFrame to a CSV file
    df.to_csv(csv_file_path, index=False)  

    row_count = len(df)
    
    # Open the file in append mode and add the row count as a footer
    with open(csv_file_path, 'a') as f:
        f.write(f"Total Records Count: {row_count}") 

    zip_file_path = csv_file_path.replace('.csv', '.csv.zip')
    
    # Create a zip file and add the CSV file to the zip
    with zipfile.ZipFile(zip_file_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        zipf.write(csv_file_path, os.path.basename(csv_file_path))
    output_file_name=os.path.basename(csv_file_path)
    os.remove(csv_file_path)
    return row_count, output_file_name
    
def move_the_file_to_winscp(sftp,timestamp):

    local_file_output = f"E:/pythonforfibe/python_FIBE/files/output/CPM_EDW_HardwareInfo_{timestamp}.csv.zip"
    remote_path_output = f"/CPM/dev/cpmbrs/output/CPM_EDW_HardwareInfo_{timestamp}.csv.zip"  
    sftp.put(local_file_output, remote_path_output)  
    print("file_move_to_winscp")

def update_the_log(connection, cursor, download_folder, process_id, ETL_start_time, timestamp_f,row_count,output_file_name):
    
    # Prepare the ETL end time using the current time and microsecond value
    ETL_end_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.") + str(timestamp_f.microsecond)[:3].rjust(3, '0')

    # Get all filenames from the input and output folders
    filenames_input = [f for f in os.listdir(download_folder) if os.path.isfile(os.path.join(download_folder, f))]
    
    # Step 2: Categorize filenames based on their naming patterns
    resourcefile = None
    prodinv_IF = None
    prodinv_LV = None
    prodinv_ARC = None
    prod_ord_file = None
    
    # Loop through each file and categorize them based on their prefix
    for filename in filenames_input:
        if filename.startswith("CPM_EDW_ProductInvInFlight_"):
            prodinv_IF=filename
        elif filename.startswith("CPM_EDW_ProductInvLive"):
            prodinv_LV=filename
        elif filename.startswith("CPM_EDW_ProductInvArchive"):
            prodinv_ARC=filename   
        elif filename.startswith("CPM_EDW_ProductOrder"):
            prod_ord_file=filename
        elif filename.startswith("CPM_EDW_Resource"):
            resourcefile=filename
    try:
        sql_query_log="Insert Into FTV_ETL_CONTROL_LOG (PROCESSID,RESOURCE_FILE,PROD_ORD_FILE,ETL_START_TIME,PROD_INV_IF_FILE,PROD_INV_LV_FILE,PROD_INV_ARC_FILE,ROW_COUNT,ETL_END_TIME,OUT_FILE) values (?,?,?,?,?,?,?,?,?,?)"
        cursor.execute(sql_query_log, (process_id,resourcefile,prod_ord_file,ETL_start_time,prodinv_IF,prodinv_LV,prodinv_ARC,row_count,ETL_end_time,output_file_name))
        connection.commit()
    except Exception as e:
        print(f"failed to insert into log table {e}")
    
def main():
    
    sftp, transport = sftp_connect()
    
    
# Call the download_files function to start downloading
    download_files(sftp, download_folder, remote_path,remote_path_RES_order)

# call temp_cleanup function
    temp_cleanup(cursor,connection)

    delta_and_attr_population(cursor,connection)

    row_count, output_file_name=generate_csvfile(engine,timestamp,sql_query)

    move_the_file_to_winscp(sftp,timestamp)

    update_the_log(connection, cursor, download_folder, process_id, ETL_start_time, timestamp_f,row_count,output_file_name)
  
#close pyodbc connection

    cursor.close()
    connection.close()
# Close the SFTP connection
    
    sftp.close()
    transport.close()
# checking if it is main func or not

if __name__ == "__main__":
 main()


