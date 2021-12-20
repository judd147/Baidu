import pandas as pd
import geopandas as gpd
import numpy as np
import tkinter as tk
from tkinter import *
from tkinter.filedialog import *
from tkinter.messagebox import *
from functools import reduce
from GCS_Conversion import gcj2wgs, wgs2gcj, gcj2bd, bd2gcj, wgs2bd, bd2wgs

#通用
def read_file(data, geofile):
    if not data:
        err1 = showerror(title='错误消息框', message='未选择数据文件！')
    if not geofile:
        err1 = showerror(title='错误消息框', message='未选择范围文件！')
    else:
        if data.__contains__('.txt'):
            df = pd.read_csv(data, sep="\t")
        else:
            err2 = showerror(title='错误消息框', message='非法数据文件类型！')
        if geofile.__contains__('.shp'):
            dfy = gpd.read_file(geofile)
        elif geofile.__contains__('.gdb'):
            lay = input("Please provide the layer name\n")
            dfy = gpd.read_file(geofile, layer=lay)
        else:
            err3 = showerror(title='错误消息框', message='非法范围文件类型！')        
    return df, dfy

def to_wgs(df):
    if df.columns.__contains__('网格中心x坐标'):
        lon = np.empty([len(df["网格中心x坐标"]), 1], dtype=float)
        lat = np.empty([len(df["网格中心y坐标"]), 1], dtype=float)   
        for i in range(len(df["网格中心x坐标"])):
            lon[i], lat[i] = gcj2wgs(df["网格中心x坐标"][i], df["网格中心y坐标"][i])
        
    elif df.columns.__contains__('网格x坐标'):
        lon = np.empty([len(df["网格x坐标"]), 1], dtype=float)
        lat = np.empty([len(df["网格y坐标"]), 1], dtype=float)   
        for i in range(len(df["网格x坐标"])):
            lon[i], lat[i] = gcj2wgs(df["网格x坐标"][i], df["网格y坐标"][i])
            
    df["x"] = lon
    df["y"] = lat
    del lon
    del lat
    return df

def agg_time(df):
    df = df.groupby(['网格ID','网格中心x坐标','网格中心y坐标','x','y']).aggregate({'人数': 'sum'}).reset_index()
    return df

def intersect(df, dfy):
    dfx = gpd.GeoDataFrame(df, geometry = gpd.points_from_xy(df['x'], df['y']))
    dfx.crs = 'EPSG:4326' #按WGS84读取
    dfx = dfx.to_crs(epsg=4526) #转投影坐标
    dfy = dfy.to_crs(epsg=4526)
    dfb = gpd.sjoin(dfx, dfy, op='intersects') #执行相交
    return dfb

def write_file(dfb):
    file_path = asksaveasfilename(defaultextension='.csv')
    dfb.to_csv(file_path, encoding='UTF-8')
    
#客流画像专用    
def merge_num(num, df):
    dfnum = pd.read_csv(num, sep="\t")
    df.drop(columns=['网格中心x坐标','网格中心y坐标','消费水平:低','消费水平:中','消费水平:高','人生阶段:初中生','人生阶段:高中生','人生阶段:大学生','人生阶段:研究生','人生阶段:孕期','人生阶段:育儿阶段','人生阶段:家有孕妇','人生阶段:家有0-1岁小孩','人生阶段:家有1-3岁小孩','人生阶段:家有3-6岁小孩','人生阶段:家有小学生','人生阶段:家有初中生','人生阶段:家有高中生'],inplace=True)
    dfnum.drop(columns=['网格中心x坐标','网格中心y坐标'],inplace=True)
    #df[df.select_dtypes(np.float64).columns] = df.select_dtypes(np.float64).astype(np.float32)
    #dfnum[dfnum.select_dtypes(np.float64).columns] = dfnum.select_dtypes(np.float64).astype(np.float32)
    if df.columns.__contains__('小时'):
        df_final = pd.merge(df, dfnum, on = ['日期','小时','网格ID'], how = 'outer')
        df_final.update(df_final.iloc[:, 3:51].mul(df_final.人数, 0))
    else:
        df_final = pd.merge(df, dfnum, on = ['日期','网格ID'], how = 'outer')
        df_final.update(df_final.iloc[:, 2:50].mul(df_final.人数, 0))
    return df_final

#常住画像专用
def merge_res(num, df):
    dfnum = pd.read_csv(num, sep="\t")
    df.drop(columns=['网格x坐标','网格y坐标','消费水平:低','消费水平:中','消费水平:高','人生阶段:初中生','人生阶段:高中生','人生阶段:大学生','人生阶段:研究生','人生阶段:孕期','人生阶段:育儿阶段','人生阶段:家有孕妇','人生阶段:家有0-1岁小孩','人生阶段:家有1-3岁小孩','人生阶段:家有3-6岁小孩','人生阶段:家有小学生','人生阶段:家有初中生','人生阶段:家有高中生'],inplace=True)
    dfnum.drop(columns=['网格x坐标','网格y坐标'],inplace=True)
    df_final = pd.merge(df, dfnum, on = ['日期','网格ID','区域名称','人口类型'], how = 'outer')
    df_final.update(df_final.iloc[:, 4:52].mul(df_final.人数, 0))
    return df_final

#OD专用
def OD_to_wgs(df):
    if df.columns.__contains__('起点网格中心x坐标'):
        lon = np.empty([len(df["起点网格中心x坐标"]), 1], dtype=float)
        lat = np.empty([len(df["起点网格中心y坐标"]), 1], dtype=float)   
        for i in range(len(df["起点网格中心x坐标"])):
            lon[i], lat[i] = gcj2wgs(df["起点网格中心x坐标"][i], df["起点网格中心y坐标"][i])
        df["O_x"] = lon
        df["O_y"] = lat
        del lon
        del lat
        
    if df.columns.__contains__('终点网格中心x坐标'):
        lon = np.empty([len(df["终点网格中心x坐标"]), 1], dtype=float)
        lat = np.empty([len(df["终点网格中心y坐标"]), 1], dtype=float)   
        for i in range(len(df["终点网格中心x坐标"])):
            lon[i], lat[i] = gcj2wgs(df["终点网格中心x坐标"][i], df["终点网格中心y坐标"][i])
        df["D_x"] = lon
        df["D_y"] = lat
        del lon
        del lat
 
    return df

def read_OD(data, geofile, geofile2):
    df = ''
    dfy = ''
    dfy2 = ''
    if not data:
        err1 = showerror(title='错误消息框', message='未选择数据文件！')
    if not geofile and not geofile2:
        err1 = showerror(title='错误消息框', message='未选择范围文件！')
    else:
        if data.__contains__('.txt'):
            df = pd.read_csv(data, sep="\t")
        else:
            err2 = showerror(title='错误消息框', message='非法数据文件类型！')
        if geofile.__contains__('.shp'):
            dfy = gpd.read_file(geofile)
        elif geofile.__contains__('.gdb'):
            lay = input("Please provide the layer name\n")
            dfy = gpd.read_file(geofile, layer=lay)
        if geofile2.__contains__('.shp'):
            dfy2 = gpd.read_file(geofile2)
        elif geofile2.__contains__('.gdb'):
            lay2 = input("Please provide the layer name\n")
            dfy2 = gpd.read_file(geofile, layer=lay2)        
    return df, dfy, dfy2

def O_intersect(df, dfy):
    dfx = gpd.GeoDataFrame(df, geometry = gpd.points_from_xy(df['O_x'], df['O_y']))
    dfx.crs = 'EPSG:4326' #按WGS84读取
    dfx = dfx.to_crs(epsg=4526) #转投影坐标
    dfy = dfy.to_crs(epsg=4526)
    dfb = gpd.sjoin(dfx, dfy, op='intersects') #执行相交
    if dfb.columns.__contains__('index_right'):
        dfb.drop(['index_right'], axis=1, inplace=True)
    return dfb

def D_intersect(df, dfy):
    dfx = gpd.GeoDataFrame(df, geometry = gpd.points_from_xy(df['D_x'], df['D_y']))
    dfx.crs = 'EPSG:4326' #按WGS84读取
    dfx = dfx.to_crs(epsg=4526) #转投影坐标
    dfy = dfy.to_crs(epsg=4526)
    dfb = gpd.sjoin(dfx, dfy, op='intersects') #执行相交
    return dfb

#职住专用
def livework_to_wgs(df):
    if df.columns.__contains__('居住地网格中心x坐标'):
        lon = np.empty([len(df["居住地网格中心x坐标"]), 1], dtype=float)
        lat = np.empty([len(df["居住地网格中心y坐标"]), 1], dtype=float)   
        for i in range(len(df["居住地网格中心x坐标"])):
            lon[i], lat[i] = gcj2wgs(df["居住地网格中心x坐标"][i], df["居住地网格中心y坐标"][i])
        df["O_x"] = lon
        df["O_y"] = lat
        del lon
        del lat
        
    if df.columns.__contains__('工作地网格中心x坐标'):
        lon = np.empty([len(df["工作地网格中心x坐标"]), 1], dtype=float)
        lat = np.empty([len(df["工作地网格中心y坐标"]), 1], dtype=float)   
        for i in range(len(df["工作地网格中心x坐标"])):
            lon[i], lat[i] = gcj2wgs(df["工作地网格中心x坐标"][i], df["工作地网格中心y坐标"][i])
        df["D_x"] = lon
        df["D_y"] = lat
        del lon
        del lat
 
    return df

#获取文件
def get_folder(folder):
    path_ = askdirectory()
    folder.set(path_)
    
def get_file(file):
    file_ = askopenfilename()
    file.set(file_)
    
def get_geo(geo):
    geofile_ = askopenfilename()
    geo.set(geofile_)
    
def get_geo2(geo2):
    geofile_2 = askopenfilename()
    geo2.set(geofile_2)
    
#客流数量    
def num_pop(folder,file,geo):
    path = folder.get()
    data = file.get()
    geofile = geo.get()
    df, dfy = read_file(data, geofile)
    df = to_wgs(df)
    if df.columns.__contains__('小时'):
        mx = askyesno(title='消息提示框', message='检测到小时数据，请问是否要按网格合并数量')
        if mx:
            df = agg_time(df)
    dfb = intersect(df, dfy)
    info = showinfo(title='消息提示框', message='已运行成功!')
    write_file(dfb)

#客流画像    
def por_pop(folder,file,geo):
    path = folder.get()
    data = file.get()
    geofile = geo.get()
    mx1 = askyesno(title='消息提示框', message='请问是否要合并客流数量')
    df, dfy = read_file(data, geofile)
    df = to_wgs(df)
    if mx1:
        info1 = showinfo(title='消息提示框', message='请添加客流数量文件')
        num = askopenfilename()
        df = merge_num(num, df)
    dfb = intersect(df, dfy)
    info = showinfo(title='消息提示框', message='已运行成功!')
    write_file(dfb)

#常住数量
def num_longstay(folder,file,geo):
    path = folder.get()
    data = file.get()
    geofile = geo.get()
    df, dfy = read_file(data, geofile)
    df = to_wgs(df)
    dfb = intersect(df, dfy)
    info = showinfo(title='消息提示框', message='已运行成功!')
    write_file(dfb)

#常住画像
def por_longstay(folder,file,geo):
    path = folder.get()
    data = file.get()
    geofile = geo.get()
    mx2 = askyesno(title='消息提示框', message='请问是否要合并常住数量')
    df, dfy = read_file(data, geofile)
    df = to_wgs(df)
    if mx2:
        info2 = showinfo(title='消息提示框', message='请添加常住数量文件')
        num = askopenfilename()
        df = merge_res(num, df)
    dfb = intersect(df, dfy)
    info = showinfo(title='消息提示框', message='已运行成功!')
    write_file(dfb)
    
#OD分析
def num_OD(folder,file,geo,geo2):
    path = folder.get()
    data = file.get()
    geofile = geo.get()
    geofile2 = geo2.get()
    df, dfy, dfy2 = read_OD(data, geofile, geofile2)
    df = OD_to_wgs(df)
    #起点范围
    if geofile and not geofile2:
        dfb = O_intersect(df, dfy)
    #终点范围
    elif geofile2 and not geofile:
        dfb = D_intersect(df, dfy2)
    elif geofile and geofile2:
        temp = O_intersect(df, dfy)
        dfb = D_intersect(temp, dfy2)        
    info = showinfo(title='消息提示框', message='已运行成功!')
    write_file(dfb)
    
#职住数量    
def num_commute(folder,file,geo,geo2):
    path = folder.get()
    data = file.get()
    geofile = geo.get()
    geofile2 = geo2.get()
    df, dfy, dfy2 = read_OD(data, geofile, geofile2)
    df = livework_to_wgs(df)
    #起点范围
    if geofile and not geofile2:
        dfb = O_intersect(df, dfy)
    #终点范围
    elif geofile2 and not geofile:
        dfb = D_intersect(df, dfy2)
    elif geofile and geofile2:
        temp = O_intersect(df, dfy)
        dfb = D_intersect(temp, dfy2)        
    info = showinfo(title='消息提示框', message='已运行成功!')
    write_file(dfb)
    
#通勤时间    
def time_commute(folder,file,geo,geo2):
    path = folder.get()
    data = file.get()
    geofile = geo.get()
    geofile2 = geo2.get()
    df, dfy, dfy2 = read_OD(data, geofile, geofile2)
    df = livework_to_wgs(df)
    df['平均通勤时间(min)'] = df['平均通勤时间(s)']/60
    #起点范围
    if geofile and not geofile2:
        dfb = O_intersect(df, dfy)
    #终点范围
    elif geofile2 and not geofile:
        dfb = D_intersect(df, dfy2)
    elif geofile and geofile2:
        temp = O_intersect(df, dfy)
        dfb = D_intersect(temp, dfy2)        
    info = showinfo(title='消息提示框', message='已运行成功!')
    write_file(dfb)
    
window = Tk()
window.geometry('800x500')
window.title('百度数据处理')

folder = tk.StringVar()
file = tk.StringVar()
geo = tk.StringVar()
geo2 = tk.StringVar()

frame = Frame(window).pack(padx=10, pady=10)
b_path = Button(frame, width=12, text='选择文件夹', font=("宋体", 14), command=lambda:get_folder(folder)).pack(fill=X, side=LEFT, padx=10)
b_file = Button(frame, width=12, text='选择人口数据', font=("宋体", 14), command=lambda:get_file(file)).pack(side=LEFT, padx=10)
b_geo1 = Button(frame, width=12, text='选择范围(O)', font=("宋体", 14), command=lambda:get_geo(geo)).pack(side=LEFT, padx=10)
b_geo2 = Button(frame, width=12, text='选择范围(D)', font=("宋体", 14), command=lambda:get_geo2(geo2)).pack(side=LEFT, padx=10)


frame1 = Frame(window).pack(padx=10, pady=10)
b_exe1 = Button(frame1, width=10, text='客流数量', font=("宋体", 14), command=lambda:num_pop(folder,file,geo)).pack(fill=Y, padx=10, pady=5)
b_exe2 = Button(frame1, width=10, text='客流画像', font=("宋体", 14), command=lambda:por_pop(folder,file,geo)).pack(fill=Y, padx=10, pady=5)
b_exe3 = Button(frame1, width=10, text='常住数量', font=("宋体", 14), command=lambda:num_longstay(folder,file,geo)).pack(fill=Y, padx=10, pady=5)
b_exe4 = Button(frame1, width=10, text='常住画像', font=("宋体", 14), command=lambda:por_longstay(folder,file,geo)).pack(fill=Y, padx=10, pady=5)
b_exe5 = Button(frame1, width=10, text='OD分析', font=("宋体", 14), command=lambda:num_OD(folder,file,geo,geo2)).pack(fill=Y, padx=10, pady=5)
b_exe6 = Button(frame1, width=10, text='职住数量', font=("宋体", 14), command=lambda:num_commute(folder,file,geo,geo2)).pack(fill=Y, padx=10, pady=5)
b_exe7 = Button(frame1, width=10, text='通勤时间', font=("宋体", 14), command=lambda:time_commute(folder,file,geo,geo2)).pack(fill=Y, padx=10, pady=5)
b_quit = Button(frame1, width=10, text='退出', font=("宋体", 14), command=window.destroy).pack(fill=Y, padx=10, pady=5)

window.mainloop()