import tkinter as tk
import re
import threading
import queue
import datetime
import time
import os
import openpyxl
import zipfile
from tkcalendar import Calendar, DateEntry
from tkinter import filedialog, scrolledtext, ttk
from git import Repo, exc
from git.exc import GitCommandError
import shutil

# 设置环境变量 GIT_PYTHON_TRACE 为 full
os.environ["GIT_PYTHON_TRACE"] = "full"
# 设置编码为 utf-8
os.environ["PYTHONIOENCODING"] = "utf-8"
# 全局变量（目标分支选择列表）
options = None 
# 未同步代码人员名单
unmerged_commits_authors = []

def check_branch_merge(repo_path, branch1, branch2, keyword, start_date, end_date, author, queue):
    repo = Repo(repo_path)
    queue.put(f"正在拉取代码...")
    repo.remotes.origin.fetch()
    repo.git.config('--global', 'core.quotepath', 'false')
    queue.put(f"拉取代码完成")
    branch1 = branch1 if branch1.startswith('origin/') else f'origin/{branch1}'
    branch2 = branch2 if branch2.startswith('origin/') else f'origin/{branch2}'
    branch1_commits = list(repo.iter_commits(branch1))
    branch2_commits = list(repo.iter_commits(branch2))
    # queue.put(str(get_all_authors_emails(repo_path)))

    pattern = re.compile(keyword)
    unmerged_commits = []
    merged_commits = []
    files_to_compare = set()

    #将开始时间和结束时间处理为时间戳，便于比较
    start_date_timetuple = time.mktime(datetime.datetime.strptime(start_date, "%Y-%m-%d").timetuple())
    #由于控件日期默认是当天0时，所以需要将结束时间加1天
    end_date_timetuple = (datetime.datetime.strptime(end_date, "%Y-%m-%d") + datetime.timedelta(days=1)).timestamp()
    queue.put(f"以下是在{start_date}至{end_date}时间范围内，'{branch1}' 分支中包含关键字 '{keyword}' 的提交:")
    if author:
        # 遍历分支 branch1 的提交记录
        for commit in branch1_commits:
            # 过滤掉Merge branch提交
            if "Merge branch" not in commit.message:
                # 检查在时间范围内且提交消息中是否包含指定关键字 keyword，如果包含则将提交信息加入消息队列
                if pattern.search(commit.message) and start_date_timetuple <= time.mktime(commit.authored_datetime.timetuple()) <= end_date_timetuple:
                    if not author or commit.author.email == author:
                        # 时间范围内且提交消息中是否包含指定关键字 keyword的提交记录
                        queue.put(f"- {commit.author.email} {commit.hexsha}：{commit.message}")
                        if any(commit.authored_datetime == target_commit.authored_datetime for target_commit in branch2_commits):
                            merged_commits.append(commit)
                        else:
                            unmerged_commits.append(commit)
                            commit_diff_files = repo.git.show('--pretty=', '--name-only', commit.hexsha).split('\n')
                            # 将每个提交中的文件差异信息添加到一个集合 files_to_compare
                            files_to_compare.update(commit_diff_files)
        if merged_commits:
            queue.put("--------------------------------------------------------------------------------------------------------------------------------------------")
            queue.put(f"以下在{start_date}至{end_date}时间范围内包含关键字 '{keyword}' 的提交已从 '{branch1}' 合并到 '{branch2}':")
            for commit in merged_commits:
                queue.put(f"- {commit.author.email} {commit.hexsha}：{commit.message}")
        
        if unmerged_commits:
            all_files_same = True
            different_files = []
            uncompare_files = []

            queue.put("--------------------------------------------------------------------------------------------------------------------------------------------")
            queue.put(f"请检查以下在{start_date}至{end_date}时间范围内包含关键字 '{keyword}' 未使用遴选方式的提交，可能未从 '{branch1}' 合并到 '{branch2}':")
            for commit in unmerged_commits:
                queue.put(f"- {commit.author.email} {commit.hexsha}：{commit.message}")   

            for file in files_to_compare:
                if file:
                    try:
                        diff = repo.git.diff(f"{branch1}:{file}", f"{branch2}:{file}", '--ignore-space-at-eol', '-w', '--ignore-cr-at-eol')
                        if diff:
                            all_files_same = False
                            different_files.append(file)
                        else:
                            pass
                    except GitCommandError as e:
                        uncompare_files.append(file)
            # 输出差异文件
            if different_files:
                queue.put("--------------------------------------------------------------------------------------------------------------------------------------------")
                queue.put("以下是未通过遴选方式提交存在的差异文件：")
                for file in different_files:
                    queue.put(f"  -{file}")
                queue.put("文件存在差异并不意味着是本次提交未同步代码造成，也可能是其他提交未同步导致文件存在差异，请人工检测")
            else:
                queue.put("暂无差异文件")
            
            # 输出无法比较文件
            if uncompare_files:
                queue.put("--------------------------------------------------------------------------------------------------------------------------------------------")
                queue.put("以下是无法比较的文件，这些文件可能是在某个分支上是新增的，或者已经被删除：")
                for file in uncompare_files:
                    queue.put(f"  -{file}")
            
            if files_to_compare and all_files_same:
                queue.put("--------------------------------------------------------------------------------------------------------------------------------------------")
                queue.put(f"所有在{start_date}至{end_date}时间范围内包含关键字 '{keyword}' 的提交中修改的文件，在 '{branch1}' 和 '{branch2}' 中内容相同，可能已通过其它方式手工合并。")
            
        else:
            queue.put(f"所有在{start_date}至{end_date}时间范围内包含关键字 '{keyword}' 的提交，已通过遴选的方式从 '{branch1}' 合并到 '{branch2}")

    else:
        authors = get_all_authors_emails(repo_path)

        for author_email in authors:
            queue.put(f"-----------------------------------------------------------------------------{author_email} 的代码合并情况-----------------------------------------------------------------------------")
            check_author_merge(repo_path, branch1, branch2,  author_email, keyword, branch2_commits, start_date_timetuple, end_date_timetuple, queue)
        queue.put(f"可能存在未同步代码名单：{unmerged_commits_authors}")
        # 获取当前目录路径
        current_directory = os.getcwd()

        # 指定Excel文件路径和名称
        excel_file_path = os.path.join(current_directory, f"{start_date}至{end_date}未同步代码人员名单.xlsx")

        # 创建一个新的Excel文件
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "存在未同步代码人员名单"

        # 写入表头
        ws.append(["未同步代码人员名单"])
        # 写入未同步代码人员名单
        for author in unmerged_commits_authors:
            ws.append([author])

        # 保存Excel文件
        wb.save(excel_file_path)
        

        # 指定压缩包路径和名称
        zip_file_path = os.path.join(current_directory, f"{start_date}至{end_date}代码合并检测结果.zip")

        # 创建一个新的压缩包
        with zipfile.ZipFile(zip_file_path, 'w') as zipf:
            # 遍历当前目录下的所有文件夹
            for item in os.listdir(current_directory):
                if os.path.isdir(item) and item.endswith('代码合并检测结果'):
                    # 将文件夹及其内容添加到压缩包中
                    for root, dirs, files in os.walk(item):
                        for file in files:
                            file_path = os.path.join(root, file)
                            zipf.write(file_path, os.path.relpath(file_path, current_directory))
                        # 删除原文件夹及其内容
                        shutil.rmtree(item)
# 检查特定作者的代码合并情况
def check_author_merge(repo_path, branch1, branch2,  author, keyword, branch2_commits, start_date, end_date, queue):
    repo = Repo(repo_path)
    
    # 获取所有提交记录
    all_commits = list(repo.iter_commits())
    
    # 按关键字、时间范围和不包含 "Merge branch"进行过滤
    filtered_commits = [commit for commit in all_commits if keyword in commit.message and start_date <= time.mktime(commit.authored_datetime.timetuple()) <= end_date and commit.author.email == author and "Merge branch" not in commit.message]
    print(f"提交者数量：{len(filtered_commits)}")

    unmerged_commits = []
    merged_commits = []
    files_to_compare = set()

    if filtered_commits:
        queue.put(f"以下是'{author}'这段时间在'{branch1}'分支的提交记录:")
        merged_commits_data = []
        unmerged_commits_data = []
        different_files_data = []
        uncompare_files_data = []

        for commit in filtered_commits:
            queue.put(f"- {commit.author.email} {commit.hexsha}: {commit.message}")
            if any(commit.authored_datetime == target_commit.authored_datetime for target_commit in branch2_commits):
                merged_commits.append(commit)
            else:
                unmerged_commits.append(commit)
                commit_diff_files = repo.git.show('--pretty=', '--name-only', commit.hexsha).split('\n')
                # 将每个提交中的文件差异信息添加到一个集合 files_to_compare
                files_to_compare.update(commit_diff_files)

        if merged_commits:
            queue.put("--------------------------------------------------------------------------------------------------------------------------------------------")
            queue.put(f"以下在时间范围内包含关键字 '{keyword}' 的提交已从 '{branch1}' 合并到 '{branch2}':")
            for commit in merged_commits:
                queue.put(f"- {commit.author.email} {commit.hexsha}：{commit.message}")
                merged_commits_data.append([commit.author.email, commit.hexsha, commit.message])
        
        if unmerged_commits:
            all_files_same = True
            different_files = []
            uncompare_files = []

            queue.put("--------------------------------------------------------------------------------------------------------------------------------------------")
            queue.put(f"请检查以下在时间范围内包含关键字 '{keyword}' 未使用遴选方式的提交，可能未从 '{branch1}' 合并到 '{branch2}':")
            for commit in unmerged_commits:
                queue.put(f"- {commit.author.email} {commit.hexsha}：{commit.message}")  
                unmerged_commits_data.append([commit.author.email, commit.hexsha, commit.message])

            for file in files_to_compare:
                if file:
                    try:
                        diff = repo.git.diff(f"{branch1}:{file}", f"{branch2}:{file}", '--ignore-space-at-eol', '-w', '--ignore-cr-at-eol')
                        if diff:
                            all_files_same = False
                            different_files.append(file)
                        else:
                            pass
                    except GitCommandError as e:
                        uncompare_files.append(file)
            # 输出差异文件
            if different_files:
                queue.put("--------------------------------------------------------------------------------------------------------------------------------------------")
                queue.put("以下是未通过遴选方式提交存在的差异文件：")
                for file in different_files:
                    queue.put(f"  -{file}")
                    different_files_data.append([file])

                queue.put("文件存在差异并不意味着是本次提交未同步代码造成，也可能是其他提交未同步导致文件存在差异，请人工检测")
            else:
                queue.put("暂无差异文件")
            
            # 输出无法比较文件
            if uncompare_files:
                queue.put("--------------------------------------------------------------------------------------------------------------------------------------------")
                queue.put("以下是无法比较的文件，这些文件可能是在某个分支上是新增的，或者已经被删除：")
                for file in uncompare_files:
                    queue.put(f"  -{file}")
                    uncompare_files_data.append([file])

            if files_to_compare and all_files_same:
                queue.put("--------------------------------------------------------------------------------------------------------------------------------------------")
                queue.put(f"所有在时间范围内包含关键字 '{keyword}' 的提交中修改的文件，在 '{branch1}' 和 '{branch2}' 中内容相同，可能已通过其它方式手工合并。")
        
            
        else:
            queue.put(f"所有在时间范围内包含关键字 '{keyword}' 的提交，已通过遴选的方式从 '{branch1}' 合并到 '{branch2}")
        
        if unmerged_commits_data or different_files_data or uncompare_files_data:
            unmerged_commits_authors.append(author)
            folder_name = author +'代码合并检测结果'
            # 获取当前目录路径
            current_directory = os.getcwd()

            # 创建新文件夹在当前目录下
            new_folder_path = os.path.join(current_directory, folder_name)
            os.makedirs(new_folder_path, exist_ok=True)
            # 导出文件到指定文件夹
            if merged_commits_data:
                export_to_excel(merged_commits_data, os.path.join(new_folder_path, '已合并的提交.xlsx'), ["作者", "提交哈希值", "提交信息"])
            if unmerged_commits_data:
                export_to_excel(unmerged_commits_data, os.path.join(new_folder_path, '未合并的提交.xlsx'), ["作者", "提交哈希值", "提交信息"])
            if different_files_data:
                export_to_excel(different_files_data, os.path.join(new_folder_path, '未合并的差异文件.xlsx'), ["文件路径"])
            if uncompare_files_data:
                export_to_excel(uncompare_files_data, os.path.join(new_folder_path, '新增或删除的文件.xlsx'), ["文件路径"])

    else:
        queue.put("未找到符合条件的提交记录")    

def browse_folder():
    global options
    folder_selected = filedialog.askdirectory()
    repo_path_entry.delete(0, tk.END)
    repo_path_entry.insert(0, folder_selected)
    
    options = get_remote_branches(folder_selected)
    branch2_entry['values'] = options
    selected_option.set(options[0] if options else "")

def export_to_excel(data, file_name, header_title):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(header_title)

    for row in data:
        ws.append(row)

    wb.save(file_name)


def run_check_branch_merge():
    repo_path = repo_path_entry.get()
    branch1 = branch1_entry.get()
    branch2 = selected_option.get()
    keyword = keyword_entry.get()
    start_date = start_date_entry.get()
    end_date = end_date_entry.get()
    author = author_entry.get()
    output_text.delete(1.0, tk.END)
    try:
        if author:
            if author not in get_all_authors_emails(repo_path):
                queue.put(f"作者邮箱 '{author}' 不存在")
            else:
                threading.Thread(target=check_branch_merge, args=(repo_path, branch1, branch2, keyword, start_date, end_date, author, queue)).start()
        else:
            threading.Thread(target=check_branch_merge, args=(repo_path, branch1, branch2, keyword, start_date, end_date, author, queue)).start()
    except Exception as e:
        queue.put(str(e))


def update_output_text():
    while not queue.empty():
        message = queue.get()
        output_text.insert(tk.END, message + "\n")
    root.after(100, update_output_text)

# 检查合并
def on_submit():
    run_check_branch_merge()

# 更新目标分支选项
def update_options(event):
    value = event.widget.get()
    menu = list(event.widget['values'])
    menu.clear()
    for option in options:
        if value.lower() in option.lower():
            menu.append(option)
    event.widget['values'] = tuple(menu)

# 获取远程分支列表
def get_remote_branches(repo_path):
    repo = Repo(repo_path)
    remote_branches = [f.name for f in repo.remotes.origin.refs]
    return remote_branches

# 获取所有提交作者
# def get_all_authors(repo_path):
#     repo = Repo(repo_path)
#     all_authors = set()
#     for commit in repo.iter_commits():
#         all_authors.add(commit.author.name)
#     return list(all_authors)

# 获取所有提交作者邮箱
def get_all_authors_emails(repo_path):
    repo = Repo(repo_path)
    all_authors_emails = set()
    for commit in repo.iter_commits():
        all_authors_emails.add(commit.author.email)
    return list(all_authors_emails)

root = tk.Tk()
root.title("Check Git Branch Merge")

queue = queue.Queue()

tk.Label(root, text="项目路径:").grid(row=0, column=0, sticky="w")
repo_path_entry = tk.Entry(root, width=200)
repo_path_entry.grid(row=0, column=1)
tk.Button(root, text="请选择...", command=browse_folder).grid(row=0, column=2)

tk.Label(root, text="源分支:").grid(row=1, column=0, sticky="w")
branch1_entry = tk.Entry(root)
branch1_entry.grid(row=1, column=1, columnspan=2, sticky="ew")

tk.Label(root, text="目标分支:").grid(row=2, column=0, sticky="w")
selected_option = tk.StringVar(root)
selected_option.set("")
branch2_entry = ttk.Combobox(root, textvariable=selected_option)
branch2_entry['values'] = options
branch2_entry.bind("<KeyRelease>", update_options)
branch2_entry.grid(row=2, column=1, sticky="w")
branch2_entry.config(width=30)  # 根据需要设置适当的宽度值

tk.Label(root, text="提交关键字:").grid(row=3, column=0, sticky="w")
keyword_entry = tk.Entry(root)
keyword_entry.grid(row=3, column=1, columnspan=2, sticky="ew")

# 获取当前日期
current_date = datetime.datetime.now()
# 计算一个月前的日期
one_month_ago = current_date - datetime.timedelta(days=30)
# 格式化日期为 "%Y-%m-%d" 格式
start_date_default = one_month_ago.strftime("%Y-%m-%d")
end_date_default = current_date.strftime("%Y-%m-%d")

date_frame = tk.Frame(root)
date_frame.grid(row=4, column=0, columnspan=3, sticky="w")
tk.Label(date_frame, text="开始日期:").pack(side="left", padx=6)
start_date_entry = DateEntry(date_frame, date_pattern='yyyy-mm-dd')
start_date_entry.pack(side="left")
tk.Label(date_frame, text="结束日期:").pack(side="left", padx=6)
end_date_entry = DateEntry(date_frame, date_pattern='yyyy-mm-dd')
end_date_entry.pack(side="left")
start_date_entry.set_date(one_month_ago)
end_date_entry.set_date(current_date)

tk.Label(root, text="提交人邮箱:").grid(row=5, column=0, sticky="w")
author_entry = tk.Entry(root)
author_entry.grid(row=5, column=1, columnspan=2, sticky="ew")


submit_button = tk.Button(root, text="检查合并", command=on_submit)
submit_button.grid(row=6, column=0, columnspan=3)

# 展示域
output_text = scrolledtext.ScrolledText(root, height=50)
output_text.grid(row=10, column=0, columnspan=3, sticky="ew")


update_output_text()

root.mainloop()