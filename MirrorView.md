# MirrorView

# 设计文档

|      |      |      |      |
| :--- | :--- | :--- | :--- |
|      |      |      |      |

## 1. 项目概述

**MirrorView**是一款结合大语言模型与实时音视频技术的AI模拟面试桌面应用。用户可通过PyQt5客户端登录并与AI面试官进行多轮问答，面试过程通过摄像头实时预览，并可推流至RTMP服务器供他人旁听。系统通过唯一邀请码控制旁听权限，支持语音输入转文字及实时修正。面试结束后，AI基于对话上下文生成综合点评报告。

**技术栈**：
- **客户端**：PyQt5（界面）、OpenCV/FFmpeg（视频采集与推流）
- **后端**：Flask（API服务）、Flask-SQLAlchemy（ORM）
- **数据库**：MySQL（业务数据）、Chroma（向量数据库，基于SQLite）
- **AI**：大模型API（如GPT）、LangChain（RAG）、Whisper（语音识别）
- **流媒体**：RTMP协议 + 大疆服务器

---

## 2. 系统架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      PyQt客户端                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │登录/注册 │  │面试主界面│  │视频采集  │  │RTMP推流  │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│       ↑              ↑              ↑              ↑        │
└──────────┬───────────┬──────────────┬───────────┬───────────┘
           │ HTTP API   │ HTTP API     │ WebSocket │ RTMP
           ↓             ↓              ↓           ↓
┌─────────────────────────────────────────────────────────────┐
│                       Flask后端                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │REST API  │  │AI服务模块│  │会话管理  │  │邀请码生成│   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│       ↑              ↑              ↑              ↑        │
└──────────┬───────────┬──────────────┬───────────┬───────────┘
           │ SQLAlchemy │ SQLAlchemy   │ LangChain │
           ↓             ↓              ↓           ↓
┌─────────────────────────────────────────────────────────────┐
│                         数据层                               │
│  ┌────────────────────┐  ┌────────────────────┐           │
│  │   SQLite数据库     │  │   Chroma向量库     │           │
│  │ (业务数据:用户、   │  │ (面试知识库、      │           │
│  │  面试记录、对话)   │  │  向量检索)         │           │
│  └────────────────────┘  └────────────────────┘           │
└─────────────────────────────────────────────────────────────┘
                           ↑
                           | RTMP推流
┌─────────────────────────────────────────────────────────────┐
│                     大疆RTMP服务器                           │                           │
└─────────────────────────────────────────────────────────────┘
                           ↑
                           | RTMP拉流（旁听者通过浏览器/VLC访问）
```

---

应用窗口大小实现自适应，通过计算比例来调整每个控件的大小

## 3. 功能介绍

### 3.1 登录

**功能描述**：
- 用户输入用户名/邮箱和密码进行登录
- 支持记住密码（本地存储token）
- 登录成功后跳转至面试主界面

**注意事项**：
- 密码传输需加密（HTTPS + JWT token）
- 登录状态需本地持久化（使用PyQt的QSettings）
- 登录失败给出明确提示

### 3.2 注册

**功能描述**：
- 新用户填写用户名、邮箱、密码、确认密码
- 可选填写求职意向（岗位类型、工作年限）
- 注册成功后自动登录或跳转至登录页

**注意事项**：
- 邮箱格式验证、密码复杂度校验
- 用户名/邮箱唯一性校验（后端接口实时验证）
- 注册信息存入`users`表

### 3.3 视频播放

**功能描述**：
- 打开本地摄像头，在PyQt界面中央区域实时显示画面
- 支持画面比例调整（适应窗口）
- 显示录制状态指示灯（红色圆点）

**技术实现**：
- 使用OpenCV捕获摄像头帧（`cv2.VideoCapture`）
- 通过PyQt的`QLabel`或`QGraphicsView`显示帧图像
- 定时器（QTimer）刷新画面（约30fps）

**注意事项**：

- 摄像头权限申请(可以使用ffmpeg或opencv)

  

### 3.4 开始模拟面试

**功能描述**：
- 用户选择面试岗位、难度、时长后点击"开始面试"
- 系统创建新的面试记录（状态为"进行中"）
- AI面试官进行开场白并开始提问
- 面试过程中，用户可通过语音或文本回答问题

**注意事项**：
- 同一用户不能同时进行多场面试（前端禁用+后端并发控制）
- 面试开始后自动开启摄像头和推流
- 面试状态机管理：待开始 → 进行中 → 已结束 → 点评完成

### 3.5 生成邀请码

**功能描述**：
- 面试开始后，用户可点击"生成邀请码"按钮
- 系统生成8-10位唯一邀请码（字母数字组合）
- 邀请码默认有效期为24小时，最大使用次数10次
- 支持复制邀请码

**邀请码生成算法**：

```
def generate_invite_code(interview_id, user_id, timestamp):
    # 组合数据源：面试ID + 用户ID + 时间戳
    raw = f"{interview_id}-{user_id}-{timestamp}"
    # 使用Hashids库编码为短字符串（避免直接暴露数据库ID）
    import hashids
    hasher = hashids.Hashids(salt="your-secret-salt", min_length=8)
    code = hasher.encode(interview_id, user_id, int(timestamp))
    return code[:10]  # 截取前10位
```

**注意事项**：
- 邀请码需存入数据库`invite_codes`表，并建立唯一索引
- 需校验不重复（若碰撞则重新生成）
- 支持邀请码失效（过期/达最大使用次数后自动禁用）

### 3.6 加入他人面试

**功能描述**：
- 旁听者在客户端输入邀请码
- 系统验证邀请码有效性（未过期、未达最大次数）
- 验证通过后，获取对应面试的RTMP播放地址
- 在PyQt窗口中播放面试实况（仅视频，无音频输入权限）

**技术实现**：
- PyQt中集成VLC或FFmpeg播放RTMP流
- 使用`libvlc`的Python绑定或`QMediaPlayer`（需确认支持RTMP）

**注意事项**：
- 旁听者不能进行任何交互（不能发言、不能控制面试进程）
- 记录旁听日志（`listeners`表）

### 3.7 Agent问答

**功能描述**：
- **提问阶段**：AI面试官根据岗位要求进行结构化提问
- **回答阶段**：
  - 语音输入：用户说话 → 语音识别（Whisper）→ 转文字填入文本框
  - 文本输入：用户可直接在文本框修改识别结果
  - 发送后，AI根据回答进行简短串联（如"好的，那我们聊聊下一个问题"）
- **防闲聊机制**：AI严格限定为面试官角色，识别非面试内容时引导回正题

**技术实现**：
- 语音识别：本地部署Whisper或调用云API

- 大模型调用：阿里云百炼api

  ~~~
  api_key="sk-your-dashscope-key"
  ~~~

- Prompt工程：
  ```
  你是一位严格的{岗位}面试官。你的职责是：
  1. 根据岗位要求提问
  2. 对用户的回答做简短回应（如"好的"、"明白"），不要评价对错
  3. 然后提出下一个问题
  4. 如果用户试图闲聊，请回复"请回答面试问题"
  5. 所有问题问完后，告知用户"面试结束，正在生成点评"
  ```

**注意事项**：
- 保存每轮对话到`messages`表，用于后续RAG检索和点评
- 语音识别错误处理：保留原始文本，允许用户修改后再提交
- 上下文管理：维护最近N轮对话，避免token超限

### 3.8 Agent点评复盘

**功能描述**：
- 面试结束后（所有预设问题问完或用户主动结束），AI生成综合点评报告
- 报告内容包括：
  - 总体评分（百分制/星级）
  - 各维度表现（技术掌握度/表达能力/反应速度等）
  - 优点总结（3-5点）
  - 待改进项（3-5点）
  - 学习资源推荐（基于知识库检索）
- 报告存入数据库，用户可在历史记录中查看

**技术实现**：
- 从`messages`表提取该面试的所有对话
- 从`knowledge_embeddings`检索相关知识点（RAG增强）
- 构建点评Prompt调用大模型生成结构化报告
- 报告以JSON格式存入`interviews.overall_feedback`字段

**注意事项**：
- 点评生成可能耗时较长，可采用异步任务（如Celery）
- 点评结果需在前端友好展示（Markdown渲染）
- 支持导出PDF/分享报告

---

## 4. 新增/补充功能

### 4.1 RTMP推流

`rtmp`地址

~~~
rtmp://116.62.11.13:1935/live/pull
~~~

### 4.2 历史记录与回放

**功能描述**：
- 用户可查看自己所有的面试历史记录
- 每场面试显示时间、岗位、评分、状态
- 点击可查看详细对话和点评报告

### 4.3 面试中断恢复

**功能描述**：
- 若面试过程中网络中断或提前退出，重新登录后可选择继续未完成的面试
- 保留已完成的对话记录和上下文

**注意事项**：
- 面试状态需实时同步到后端
- 恢复时需重新初始化AI上下文



---

## 5. 数据库设计（SQLite + Flask-SQLAlchemy）

由于采用MySQL作为业务数据库，Chroma作为向量数据库（基于SQLite），两者独立。

### 1. 用户表 （users）

| 字段名        | 数据类型     | 约束                      | 含义说明                       |
| :------------ | :----------- | :------------------------ | :----------------------------- |
| id            | INTEGER      | PRIMARY KEY AUTOINCREMENT | 用户唯一标识                   |
| username      | VARCHAR(50)  | NOT NULL UNIQUE           | 用户名                         |
| password_hash | VARCHAR(128) | NOT NULL                  | 加密后的密码                   |
| email         | VARCHAR(100) | NOT NULL UNIQUE           | 电子邮箱                       |
| avatar        | VARCHAR(200) |                           | 头像文件路径                   |
| job_intention | VARCHAR(100) |                           | 求职意向（如：Java开发工程师） |
| work_years    | INTEGER      | DEFAULT 0                 | 工作年限（0表示应届）          |
| is_active     | BOOLEAN      | DEFAULT 1                 | 账号状态：0-禁用，1-正常       |
| last_login    | DATETIME     |                           | 最后登录时间                   |
| created_at    | DATETIME     | DEFAULT CURRENT_TIMESTAMP | 注册时间                       |

### 2. 面试记录表 （interviews）

| 字段名           | 数据类型     | 约束                              | 含义说明                                       |
| :--------------- | :----------- | :-------------------------------- | :--------------------------------------------- |
| id               | INTEGER      | PRIMARY KEY AUTOINCREMENT         | 面试ID                                         |
| user_id          | INTEGER      | FOREIGN KEY （users.id） NOT NULL | 面试者ID                                       |
| title            | VARCHAR(200) |                                   | 面试标题（如“Java开发面试-20240311”）          |
| job_position     | VARCHAR(100) | NOT NULL                          | 具体岗位（如：Java后端）                       |
| difficulty       | VARCHAR(20)  | DEFAULT 'medium'                  | 难度（easy/medium/hard）                       |
| duration         | INTEGER      |                                   | 计划时长（分钟）                               |
| status           | INTEGER      | DEFAULT 0                         | 状态：0-待开始，1-进行中，2-已结束，3-点评完成 |
| rtmp_push_url    | VARCHAR(200) |                                   | RTMP推流地址                                   |
| rtmp_play_url    | VARCHAR(200) |                                   | RTMP播放地址（用于旁听）                       |
| start_time       | DATETIME     |                                   | 实际开始时间                                   |
| end_time         | DATETIME     |                                   | 实际结束时间                                   |
| total_score      | FLOAT        |                                   | 综合评分（百分制）                             |
| overall_feedback | TEXT         |                                   | 综合点评报告（JSON格式）                       |
| created_at       | DATETIME     | DEFAULT CURRENT_TIMESTAMP         | 创建时间                                       |

### 3. 对话记录表 （messages）

| 字段名           | 数据类型    | 约束                                   | 含义说明                          |
| :--------------- | :---------- | :------------------------------------- | :-------------------------------- |
| id               | INTEGER     | PRIMARY KEY AUTOINCREMENT              | 消息ID                            |
| interview_id     | INTEGER     | FOREIGN KEY （interviews.id） NOT NULL | 所属面试ID                        |
| role             | VARCHAR(10) | NOT NULL                               | 发送者角色：'user' 或 'agent'     |
| content          | TEXT        | NOT NULL                               | 最终发送内容（用户修改后/AI生成） |
| original_content | TEXT        |                                        | 原始语音识别内容（仅user角色有）  |
| asr_confidence   | FLOAT       |                                        | 语音识别置信度（0-1）             |
| response_time    | INTEGER     |                                        | 用户回答耗时（秒）                |
| question_type    | VARCHAR(50) |                                        | 问题类型（技术/项目/情景/软技能） |
| created_at       | DATETIME    | DEFAULT CURRENT_TIMESTAMP              | 发送时间                          |

### 4. 邀请码表 （invite_codes）

| 字段名       | 数据类型    | 约束                                   | 含义说明               |
| :----------- | :---------- | :------------------------------------- | :--------------------- |
| id           | INTEGER     | PRIMARY KEY AUTOINCREMENT              | 邀请码ID               |
| code         | VARCHAR(20) | NOT NULL UNIQUE                        | 邀请码字符串（8-10位） |
| interview_id | INTEGER     | FOREIGN KEY （interviews.id） NOT NULL | 关联面试ID             |
| created_by   | INTEGER     | FOREIGN KEY （users.id）               | 生成者ID               |
| max_uses     | INTEGER     | DEFAULT 10                             | 最大使用次数           |
| current_uses | INTEGER     | DEFAULT 0                              | 当前已使用次数         |
| expires_at   | DATETIME    |                                        | 过期时间               |
| is_active    | BOOLEAN     | DEFAULT 1                              | 状态：0-禁用，1-有效   |
| created_at   | DATETIME    | DEFAULT CURRENT_TIMESTAMP              | 生成时间               |

### 5. 旁听记录表 （listeners）

| 字段名         | 数据类型     | 约束                                   | 含义说明                   |
| :------------- | :----------- | :------------------------------------- | :------------------------- |
| id             | INTEGER      | PRIMARY KEY AUTOINCREMENT              | 记录ID                     |
| interview_id   | INTEGER      | FOREIGN KEY （interviews.id） NOT NULL | 面试ID                     |
| invite_code_id | INTEGER      | FOREIGN KEY （invite_codes.id）        | 使用的邀请码ID             |
| listener_id    | VARCHAR(100) |                                        | 旁听者标识（如IP或设备ID） |
| listener_name  | VARCHAR(50)  |                                        | 旁听者昵称（自行输入）     |
| joined_at      | DATETIME     | DEFAULT CURRENT_TIMESTAMP              | 加入时间                   |
| left_at        | DATETIME     |                                        | 离开时间                   |
| watch_duration | INTEGER      |                                        | 观看时长（秒）             |

### 

### 5.2 Chroma向量数据库

Chroma基于SQLite，无需额外服务，适合桌面应用。

### 5.3 数据库关系图

```
┌─────────┐       ┌────────────┐       ┌─────────┐
│ users   │       │ interviews │       │ messages│
│─────────│       │────────────│       │─────────│
│ id      │──────▶│ user_id    │       │ id      │
│ username│       │ id         │◀──────│ interview_id
│ ...     │       │ ...        │       │ ...     │
└─────────┘       └────────────┘       └─────────┘
                        │
                        │
                        ▼
                  ┌────────────┐       ┌────────────┐
                  │invite_codes│       │ listeners  │
                  │────────────│       │────────────│
                  │ id         │       │ id         │
                  │ interview_id│─────▶│interview_id│
                  │ code       │       │invite_code_id
                  │ ...        │       │ ...        │
                  └────────────┘       └────────────┘
```

---

## 6. 技术难点与解决方案

| 难点                     | 解决方案                                                 |
| :----------------------- | :------------------------------------------------------- |
| **PyQt中实时显示摄像头** | OpenCV采集 + QTimer刷新QPixmap，注意线程分离避免界面卡顿 |
| **RTMP推流集成**         | 使用ffmpeg子进程 + 管道传输OpenCV帧，简单可靠            |
| **语音识别实时性**       | 本地Whisper（small模型）或云API，结合缓冲区优化          |
| **大模型响应速度**       | 流式输出（SSE），在PyQt中逐步显示AI回复                  |
| **邀请码唯一性**         | Hashids编码 + 数据库唯一约束 + 碰撞重试                  |
| **Chroma与SQLite共存**   | Chroma独立存储路径，与Flask-SQLAlchemy互不干扰           |
| **面试状态保持**         | 前端定时同步+后端状态机，异常中断支持恢复                |
| **RAG检索效率**          | Chroma向量索引 + 结果缓存，避免重复检索                  |

---

