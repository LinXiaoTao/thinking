# 优化

优化包含**渲染优化**、**内存优化**、**网络优化**、**电量优化**、**性能优化**、**包体积优化**。

如果从用户角度来看的话：

* 用电更少
* 启动更快
* 交互更快

## 性能监控

性能监控可以分为测试环境和线上环境。

代码增强工具：[booster](git@github.com:didi/booster.git)

跨端网络请求框架：[mars](https://github.com/Tencent/mars)

线上性能监控：[matrix](https://github.com/Tencent/matrix)

开发小工具：[DoraemonKit](https://github.com/didi/DoraemonKit)

代码层面监控：[StrictMode](https://developer.android.com/reference/android/os/StrictMode)

## 电量优化

### 唤醒锁操作卡住

**问题原因**：

使用 `PowerManager` API 可以在设备屏幕关闭的时候依然保持 CPU 处于运行状态。通过使用 `PARTIAL_WAKE_LOCK` 标记调用 `acquire()` 函数，可以获取一个局部唤醒锁，如果持有唤醒锁的操作卡住，会导致设备在熄屏的情况不能进入低功耗模式，消耗大量的电量。

> 关于  PowerManager.newWakeLocak 方法
>
> 需要 Manifest.permission.WAKE_LOCK 权限。
>
> 这个方法有两个参数：int levelAndFlags 和 String tag
>
> 可选的 level 有：
>
> * PARTIAL_WAKE_LOCK：确保  CPU 执行，屏幕和键盘背光可以关闭
> * FULL_WAKE_LOCK：确保 CPU、屏幕和键盘背光全打开，API 17 后弃用，可以使用 `WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON` 代替
> * SCREEN_DIM_WAKE_LOCK：确保屏幕（变暗）打开，屏幕背光关闭，API 17 后弃用，可以使用 `WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON` 代替
> * SCREEN_BRIGHT_WAKE_LOCK：确保屏幕全亮度打开，屏幕背光关闭，API 15 后弃用，可以使用 `WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON` 代替
>
> 可选的 flag 有：
>
> * ACQUIRE_CAUSES_WAKEUP：获取唤醒锁后开启屏幕
> * ON_AFTER_RELEASE：释放唤醒锁后，让屏幕显示再停留会

**定位问题**：

* [dumpsys](https://source.android.com/devices/tech/debug/dumpsys) 可以用于提供当前设备上系统服务的状态信息，如果用获取电量相关的信息，可以使用 `adb shell dumpsys power`。
* [Battery Historian](https://developer.android.com/topic/performance/power/battery-historian.html) 可以将 [bug report](https://developer.android.com/studio/debug/bug-report.html) 的输出中与电源相关的事件解析为直观表示。

**解决问题**：

从长远来看，使用新的 `WorkManager` API 更能解决问题。如果还是使用唤醒锁的方式的话，在使用 `newWakeLock(int,String)` 或者 `WakefulBroadcastReceiver` 时，增加使用唤醒锁的标记，用于定位问题，并确保及时释放锁。

* 推荐使用包含包名、类名、方法名等信息来标记唤醒锁，这样可以快速定位到源码中创建唤醒锁的位置。

  关于标记的命名有一些提示：

  - 不能使用任何个人身份信息，比如邮箱等，否则设备日志将会用 `_UNKONWN` 来代替。
  - 不要用代码的时候获取类名或者方法，比如使用 `getName`，因为代码混淆工具会对它进行优化，推荐使用硬编码。
  - 不要通过计数器或者唯一标示来命名，这样，系统没办法聚合通过相同方法创建的唤醒锁。

* 确保代码中已经释放了所有申请的唤醒锁。

  ``` kotlin
  @Throws(MyException::class)
  fun doSomethingAndRelease() {
      wakeLock.apply {
          try {
              acquire()
              doSomethingThatThrows()
          } finally {
              release()
          }
      }
  }
  ```

* 确保唤醒锁不再需要的时候，及时被释放。

### 频繁唤醒

**问题原因**：

可以通过使用 `AlarmManager` API来让系统在某个时间启动应用执行。Alarm Manager 本身会在 `onReceive()` 方法执行时，保持 CPU 唤醒锁，在方法执行完后，再释放。在调用 `AlarmManager.set()` 方法时，使用 `RTC_WAKEUP` 和 `ELAPSED_REALTIME_WAKEUP` 标志，则会唤醒设备。频繁唤醒设备会消耗大量电量。

> 在 API 19 之前，可以通过调用 `AlarmManager.set(int,long,PendingIntent)` 方法来安排一次警报事件，在 API 19 之后，这个方法设置的实际触发时间将不再精确，因为系统会通过批处理警报事件，以减少频繁唤醒系统。可以使用 `AlarmManager.setWindow(int,long,long,PendingIntent)` 和 `AlarmManager.setExact(int,long,PendingIntent)` 代替。
>
> 通过 `set()` 方法注册的警报，在手机处于低功耗的情况下，并不会执行，可以使用 `setAndAllowWhileIdle()` 方法，在这个方法注册的警报有频率限制，比如当手机处理低功耗模式下，为 15 分钟。同时会批处理这类警报。
>
> 警报类型：
>
> * RTC_WAKEUP：使用 `System.currentTimeMillis` 计算时间，会唤醒设备
> * RTC：使用 `System.currentTimeMillis` 计算时间，不会唤醒设备
> * ELAPSED_REALTIME_WAKEUP：使用 `SystemClock.elapsedRealtime` 计算时间，会唤醒设备
> * ELAPSED_REALTIME：使用 `SystemClock.elapsedRealtime` 计算时间，不会唤醒设备

**解决问题**：

可以使用 `WorkManager` API 来代替 `AlarmManager` API 实现相同的需求。

* 推荐使用包含包名、类名、方法名等信息来标记警报设置，这样可以快速定位到源码中设置警报的位置。

  关于标记的命名有一些提示：

  - 不能使用任何个人身份信息，比如邮箱等，否则设备日志将会用 `_UNKONWN` 来代替。
  - 不要用代码的时候获取类名或者方法，比如使用 `getName`，因为代码混淆工具会对它进行优化，推荐使用硬编码。
  - 不要通过计数器或者唯一标示来命名，这样，系统没办法聚合通过相同方法设置的警报。

* [AlarmManager 的最佳实践](https://developer.android.com/training/scheduling/alarms)

### 后台 WIFI 扫描次数过多

### 后台网络使用量过高

## ANR

**问题原因**：

根本原因是长时间阻塞主线程

1. Network / Disk 操作
2. 长时间计算
3. IPC 操作
4. 锁和同步
5. 死锁
6. Broadcast.onReceive

**发现问题**：

* [StrictMode](https://developer.android.com/reference/android/os/StrictMode.html)
* 启用**显示所有"应用无响应(ANR)"**选项
* [Traceview](https://developer.android.com/studio/profile/traceview.html)
* traces file

**解决问题**：

* 可以将耗时操作或者 IO 操作移动到工作线程
* 避免主线程阻塞在长时间的等待锁释放中
* 避免死锁
* 可以将耗时操作移动到 `IntentSerivce` 中实现，也可以同时使用 `goAsync()` 方法通知系统需要更长的时间来处理消息，最后需要调用 `finish()` 方法通知结束。

## 渲染优化

可以用于在调试模式下定位问题：

* Systrace
* CPU Profiler

使用 Systrace 使用颜色突出显示每一帧中渲染比较慢的部分，配合 CPU Profiler 中 method trace 功能，排查耗时方法，再重新使用 Systrace 添加跟踪标记，再重新使用 Systrace 定位问题。

> 当使用 Systrace 时，每一个跟踪标记会占用大概 10us，所以为了确保误判，不要将跟踪标记添加到一帧里面会调用数十次的方法，或者执行时间少于 200us 的方法。

常见的 jank 场景：

Scrollable lists

* RecyclerView: notifyDataSetChanged

  可以使用 DiffUtil 代替

* RecyclerView: Nested RecyclerViews

  * 复用 RecyclerView.Pool
  * 通过 `setInitialPrefetchItemCount(int)` 在空闲时间预取 Item

* RecyclerView: Too much inflation / Create taking too long

  Item 视图应该尽可能的简单

* RecyclerView: Bind taking too long

* RecyclerView or ListView: layout / draw taking too long

* ListView: Inflation

  复用已经传递进来的 convertView

Layout performance

* Layout performance: Cost

  避免使用 RelativeLayout 和 带权重的 LinearLayout，可以使用 ConstraintLayout 代替

* Layout performance: Frequency

  通常重绘的成本要低于布局的成本

Rendering performance

Android UI 绘制工作在两个阶段，**Record View#draw** 在 UI 线程，而 **DrawFrame** 在 Render 线程。

* Rendering performance: UI Thread

  通常在 UI 线程上绘制 bitmap，使用 CPU 渲染。我们可以在后台线程处理后，再交给 Canvas 绘制。也可以使用 `setLayerType()` 设置 `LAYER_TYPE_HARDWARE` 来缓存渲染输出，仍使用 GPU 渲染。

* Rendering performance: RenderThread

  一些操作对于 Canvas 来说是很廉价的，但对于 RenderThread 来说，却很昂贵。

  * Canvas.saveLayer()

    它会触发昂贵的离屏渲染，虽然在 Android 6.0 进行了优化。确包你至少传递了 Canvas.CLIP_TO_LAYER_SAVE_FLAG。

  * Canvas.drawPath

    在支持硬件加速的设备上，调用 `drawPath`，会先在 CPU 上绘制这些路径，然后再上传到 GPU。可以更多的使用 `drawPoints()` 、`drawLines()` 、`drawRect/Circle/Oval/RoundRect()` 这些方法。

  * Canvas.clipPath

    昂贵的操作应该避免，比如可以使用 BitmapShader 等代替。

  * Bitamp uploads

    > Upload width x height Texture

    Android 用 OpenGl 纹理显示 bitmaps 对象，它需要先上传到 GPU 中。

    避免上传不合适大小的 Bitamp，Android 7.0 之后支持调用 `prepareToDraw()` 提前上传 bitmap 到 GPU。

Thread scheduling delays

Systrace 使用不同的颜色来表示当前线程的运行状态：

* 灰色表示当前线程在休眠
* 蓝色表示当前线程可运行，但调度器还没有选择让它运行
* 绿色表示当前线程正在运行
* 红色或橙色表示当前线程在不间断休眠

> 在 Android 旧版本上，很多的调度问题不是应用本身的问题，尽量在新版本上进行调试。
>
> 有一些调度是正常现象，比如 UI 线程被阻塞，而 RenderThread 的 `syncFrameState` 正在运行，同时 bitmaps 正在上传，这是正常的，这样 RenderTherad 才能安全的从 UI 线程拷贝数据。还有一个例子，RenderThread 调用 IPC 时被阻塞：在每一帧开始的时候获取缓冲，从上面查询信息，或者使用 `eglSwapBuffers` 将缓冲传递回合成器。

大部分情况下，这种暂停是因为 binder 调用导致的，减少这种直接的 binder 调用，可以缓存结果或者移动到后台线程中进行。可以使用 adb 来快速定位这类问题：

``` shell
adb shell am trace-ipc start
adb shell am trace-ipc stop --dump-file /data/local/tmp/ipc-trace.txt
adb pull /data/local/tmp/ipc-trace.txt
```

还有一些情况是因为主线程在等待其他线程的锁，应该尽量避免这种情况。

Object allocation and garbage collection

在最近的 Android 版本中，用使用一个叫做 **HeapTaskDaemon** 的后台线程进行 GC 工作。





## 

