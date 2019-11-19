## 参考文章

[Flutter渲染机制—UI线程](http://gityuan.com/2019/06/15/flutter_ui_draw/)

[Flutter渲染机制—GPU线程](http://gityuan.com/2019/06/16/flutter_gpu_draw/)

[理解 VSync](https://blog.csdn.net/zhaizu/article/details/51882768)

## 预备知识

### 关于 60FPS

在衡量一个 APP 是否流畅的时候，经常会用 FPS 这个指标，FPS(Frames Per Second) 表示屏幕每秒传输帧数，60 FPS 则表示每秒传输 60 帧。一般来说，FPS 越高，画面就会越流畅，一般电影会使用 24FPS ~ 30FPS，但对于 Android 设备来说，60FPS 则是目前来说的 "最优解"，不排除以后会有更高数值。

![fps](https://timgsa.baidu.com/timg?image&quality=80&size=b9999_10000&sec=1572598351172&di=9f08e97c7ba19c7a40bccf2d77311ce9&imgtype=0&src=http%3A%2F%2Fimg.mp.itc.cn%2Fupload%2F20161111%2F0062bbd9f9f5451d88751f734bcdf096.gif)



> 对于为什么 60FPS 是最优解，有兴趣可以了解下：[Why 60fps?](https://www.youtube.com/watch?v=CaMTIgxCSqU)

60FPS 中一帧从绘制到同步，不能超过 16.6(1000 ms / 60) ms，超过这个值，就会发生掉帧，就是我们说的卡顿。

### 硬件加速

硬件加速这个名词，在 wiki 中的定义如下：

> **硬件加速**是指在[计算机](https://zh.wikipedia.org/wiki/计算机)中通过把计算量非常大的工作分配给专门的[硬件](https://zh.wikipedia.org/wiki/硬件)来处理以减轻[中央处理器](https://zh.wikipedia.org/wiki/中央处理器)的工作量之技术。尤其是在图像处理中这个技术经常被使用。

在 Android 设备中，硬件加速指的是将一部分的绘制任务转移到 GPU 中去处理，从而减轻 CPU 的负担。Android 3.0 开启支持硬件加速，4.0 之后默认开启。

### VSync

VSync(Vertical Synchronization) 表示垂直信号同步，为什么需要这个东西呢？因为屏幕本身有自己的刷新频率，比如 60HZ，这表示屏幕每次刷新的次数，而从 CPU 或 GPU 传输图像数据的速度并不一定和屏幕刷新率保持一致，这样会导致页面发生"撕裂"的情况，如下图：

![Tearing](https://user-gold-cdn.xitu.io/2019/10/23/16df6b46037ea609?w=333&h=185&f=png&s=5056)



Android 4.1之后引入了 VSync 机制，同时还有多重缓存机制，首先 VSync 可以理解为一种信号，当屏幕准备好刷新时，就发出 VSync 信号通知 CPU 或 GPU 可以将数据同步到屏幕上去，这样，当 CPU 或 GPU 的帧率大于屏幕的刷新率时，VSync 信号会迫使帧率和刷新率保持一致。虽然处理了"撕裂"问题，但在等待 VSync 信号来临时，CPU 或 GPU 可能会处于空闲状态，因为它们共用一块内存，当某一帧的绘制时间过长时，会导致掉帧的情况出现。多重缓存机制就是用来解决这个问题，使用多重缓存机制后，CPU 或 GPU 会提前将图像数据绘制到缓存中，在收到 VSync 信号后，再将缓存同步到屏幕渲染的内存中。现在常用的多重缓存机制有双重缓存和三重缓存，它们的原理是一样的。

 没有使用 VSync 信号和多重缓存之前：

![img](https://img-blog.csdn.net/20160711174332761)

使用 VSync 信号和双重缓存之后：

![img](https://img-blog.csdn.net/20160711174408421)

## 概述

Flutter 相对于其他跨平台方案来说，最主要的区别之一，就是渲染机制上的不同。它既不使用 web 容器，也不使用 JS Bridge，而是使用了 Skia 绘制引擎。

> Skia 是一个开源的 2D 图形库，由 Google 开发维护，除了 Flutter 还有 Android、Chrome 浏览器等产品也使用它作为图形绘制引擎。

Flutter 的渲染机制可以用下面这张图来表示：

![Flutter Draw](http://gityuan.com/img/flutter_ui/flutter_draw.png)

Flutter 整个渲染工作可以分为两个部分：首先是 UI 线程，这部分是使用 Dart 代码编写，将 Widget 转化成 RenderObject，最终转化为 Layer Tree。接着会交由 GPU 线程去处理，这部分是在 C++ 代码编写的 Engine 层，调用 Skia Canvas 进行绘制后，再由 OpenGL 或 Vulkan 进行同步渲染。

> 除了 OpenGL 和 Vulkan 之外，还有软件渲染（Skia），当设备不支持硬件加速的时候，就会启用这种，但现在的设备基本都会支持硬件加速了，所以这种情况可以不考虑。
>
> ``` c++
> std::unique_ptr<AndroidSurface> AndroidSurface::Create(
>     bool use_software_rendering) {
>   if (use_software_rendering) {
>     // 软件渲染
>     auto software_surface = std::make_unique<AndroidSurfaceSoftware>();
>     return software_surface->IsValid() ? std::move(software_surface) : nullptr;
>   }
> #if SHELL_ENABLE_VULKAN
>   // vulkan
>   auto vulkan_surface = std::make_unique<AndroidSurfaceVulkan>();
>   return vulkan_surface->IsValid() ? std::move(vulkan_surface) : nullptr;
> #else   // SHELL_ENABLE_VULKAN
>   // OpenGL
>   auto gl_surface = std::make_unique<AndroidSurfaceGL>();
>   return gl_surface->IsOffscreenContextValid() ? std::move(gl_surface)
>                                                : nullptr;
> #endif  // SHELL_ENABLE_VULKAN
> }
> ```
>
> 关于 Vulkan，来自 [wiki](https://zh.wikipedia.org/wiki/Vulkan_(API))
>
> **Vulkan**是一个低开销、跨平台的[二维、三维图形](https://zh.wikipedia.org/wiki/计算机图形)与计算的[应用程序接口](https://zh.wikipedia.org/wiki/应用程序接口)（API），[[11\]](https://zh.wikipedia.org/wiki/Vulkan_(API)#cite_note-11)最早由[科纳斯组织](https://zh.wikipedia.org/wiki/科纳斯组织)在2015年[游戏开发者大会](https://zh.wikipedia.org/wiki/游戏开发者大会)（GDC）上发表。[[12\]](https://zh.wikipedia.org/wiki/Vulkan_(API)#cite_note-12)[[13\]](https://zh.wikipedia.org/wiki/Vulkan_(API)#cite_note-khronos-vulkan-13)与[OpenGL](https://zh.wikipedia.org/wiki/OpenGL)类似，Vulkan针对全平台即时3D图形程序（如[电子游戏](https://zh.wikipedia.org/wiki/電子遊戲)和[交互媒体](https://zh.wikipedia.org/wiki/互動式多媒體)）而设计，并提供高性能与更均衡的[CPU](https://zh.wikipedia.org/wiki/中央处理器)与[GPU](https://zh.wikipedia.org/wiki/圖形處理器)占用

## 从 VSync 开始

前面我们也说到，VSync 信号用来同步每一帧的渲染频率，在 Android 平台上，Flutter 会通过 `Choreographer` 注册 VSync 信号回调，回调的处理是在 C++ Engine 中。

``` java
Choreographer.getInstance().postFrameCallback(new Choreographer.FrameCallback() {                     
    @Override                                                                                         
    public void doFrame(long frameTimeNanos) {                                                        
        nativeOnVsync(frameTimeNanos, frameTimeNanos + refreshPeriodNanos, cookie);                   
    }                                                                                                 
});

private static native void nativeOnVsync(long frameTimeNanos, long frameTargetTimeNanos, long cookie);
```

当 Engine 接收到 VSync 信号后，会将相关处理任务发送到 UI 线程进行处理：

``` c++
void VsyncWaiter::FireCallback(fml::TimePoint frame_start_time,
                               fml::TimePoint frame_target_time) {
  
  // UI 线程
  task_runners_.GetUITaskRunner()->PostTaskForTime(
      [callback, flow_identifier, frame_start_time, frame_target_time]() {
        // 真正处理的回调方法
        callback(frame_start_time, frame_target_time);
      },
      frame_start_time);
}
```

Flutter 默认会存在四个线程，除了我们上面说到的 UI 线程以外，还有 platform、GPU、IO 这三个线程。Dart 代码运行在 UI 线程中，platform 则是 Android 或 iOS 所在的线程，GPU 线程则用于向 GPU 提交数据，IO 则是执行 IO 任务。

## UI 线程

上面我们说到，会在 UI 线程中执行一个 `callback` ，它就是 `Animator::AwaitVSync()` 方法：

``` c++
void Animator::AwaitVSync() {
  waiter_->AsyncWaitForVsync(
      [self = weak_factory_.GetWeakPtr()](fml::TimePoint frame_start_time,
                                          fml::TimePoint frame_target_time) {
        if (self) {
          if (self->CanReuseLastLayerTree()) {
            // layer tree 可复用，直接绘制
            self->DrawLastLayerTree();
          } else {
            // 否则，开始当前帧的绘制
            self->BeginFrame(frame_start_time, frame_target_time);
          }
        }
      });

  delegate_.OnAnimatorNotifyIdle(dart_frame_deadline_);
}
```

`Animator::BeginFrame()` 方法的调用链比较长，如下图所示：

![BeginFrame](https://user-gold-cdn.xitu.io/2019/10/23/16df7a376b09f48a?w=840&h=890&f=png&s=51399)

其中 C++ 和 Dart 之间的调用是通过 hooks.dart 这个文件的：

``` dart
@pragma('vm:entry-point')
// ignore: unused_element
void _beginFrame(int microseconds) {
  _invoke1<Duration>(window.onBeginFrame, window._onBeginFrameZone, new Duration(microseconds: microseconds));
}

@pragma('vm:entry-point')
// ignore: unused_element
void _drawFrame() {
  _invoke(window.onDrawFrame, window._onDrawFrameZone);
}
```

`RendererBinding` 会通过调用 `addPersistentFrameCallback()` 方法，在回调中生成每一帧绘制数据：

``` dart
void initInstances() {
  addPersistentFrameCallback(_handlePersistentFrameCallback);
}

void _handlePersistentFrameCallback(Duration timeStamp) {
    drawFrame();
}

@protected                                                                           
void drawFrame() {                                                                   
  assert(renderView != null);                                                        
  pipelineOwner.flushLayout();                                                       
  pipelineOwner.flushCompositingBits();                                              
  pipelineOwner.flushPaint();                                                        
  renderView.compositeFrame(); // this sends the bits to the GPU                     
  pipelineOwner.flushSemantics(); // this also sends the semantics to the OS.        
}                                                                                    
```

`RenderBinding` 是一个抽象类，`WidgetsBinding` 继承了它，`WidgetsBinding.drawFrame()` 方法会依此执行以下操作：构建(build)、布局(layout)、Dart层面合成(compositing bits)、绘制(paint)、GPU 合成(compositing)、语义化(semantics)。

### 构建阶段

通过调用 `Element.rebuild()`，最终调用到 `Widget.build()` 方法：

``` dart
try {
      built = build();
    } catch (e, stack) {
      built = ErrorWidget.builder(_debugReportException('building $this', e, stack));
    } finally {
      _dirty = false;
    }
    try {
      _child = updateChild(_child, built, slot);
    } catch (e, stack) {
      built = ErrorWidget.builder(_debugReportException('building $this', e, stack));
      _child = updateChild(null, built, slot);
}
```

通过调用 `updateChild()` 方法，将 `Widget` 转化为 `Element` 对象，所以说 `Widget` 在 Flutter 是一个组件配置的角色，并不会参与到最终的布局和绘制中。

### 布局阶段

通过调用 `RenderObject.performLayout()` 方法来实现，这是一个抽象方法，由 `RenderObject` 的子类各自实现：

``` dart
try {
      performLayout();
      markNeedsSemanticsUpdate();
} catch (e, stack) {
}
```

### 绘制阶段

通过调用 `RenderObject.paint()` 方法来实现，这是一个抽象方法，由 `RenderObject` 的子类各自实现：

``` dart
try {
      paint(context, offset);
    } catch (e, stack) {
}
```

### GPU 合成阶段

在 Dart 层将需要绘制的数据收集完成后，需要通过 Engine 层同步到 GPU 中进行栅格化渲染(rasterization)，最后才同步显示到屏幕上。

``` dart
void compositeFrame() {                                                                                           
  try {                                                                                                           
    final ui.SceneBuilder builder = ui.SceneBuilder();                                                            
    final ui.Scene scene = layer.buildScene(builder);                                                             
    if (automaticSystemUiAdjustment)                                                                              
      _updateSystemChrome();                                                                                      
    _window.render(scene);                                                                                        
    scene.dispose();                                                                                              
  } finally {                                                                                                     
  }                                                                                                               
}                                                                                                                 
```

这里会创建 Dart 层 和 C++ 层的 SceneBuilder 和 Scene，最终调用 `window.render()` 方法，这个方法也是 C++ 方法：

``` c++
// window.cc
void Render(Dart_NativeArguments args) {
  Dart_Handle exception = nullptr;
  Scene* scene =
      tonic::DartConverter<Scene*>::FromArguments(args, 1, exception);
  if (exception) {
    Dart_ThrowException(exception);
    return;
  }
  UIDartState::Current()->window()->client()->Render(scene);
}

// runtime_controller.cc
void RuntimeController::Render(Scene* scene) {
  client_.Render(scene->takeLayerTree());
}
```

`takeLayerTree()` 方法用于生成绘制的 layer tree，`Render()` 方法最终会调用到 `Shell.OnAnimatorDraw()` 方法。

## GPU 线程

在 `Shell.OnAnimatorDraw()` 方法中，我们会向 GPU 线程提交一个渲染任务：

``` c++
// |Animator::Delegate|
void Shell::OnAnimatorDraw(fml::RefPtr<Pipeline<flutter::LayerTree>> pipeline) {
  FML_DCHECK(is_setup_);

  task_runners_.GetGPUTaskRunner()->PostTask(
      [rasterizer = rasterizer_->GetWeakPtr(),
       pipeline = std::move(pipeline)]() {
        if (rasterizer) {
          rasterizer->Draw(pipeline);
        }
      });
}
```

`Rasterizer` 用于实现栅格化渲染，其中会使用到 Skia API 进行操作：

``` c++
bool Rasterizer::DrawToSurface(flutter::LayerTree& layer_tree) {

  auto frame = surface_->AcquireFrame(layer_tree.frame_size());

  if (frame == nullptr) {
    return false;
  }
	
  // skia 绘制
  auto* canvas = frame->SkiaCanvas();

  auto compositor_frame = compositor_context_->AcquireFrame(
      surface_->GetContext(), canvas, external_view_embedder,
      surface_->GetRootTransformation(), true);
	
  // 调用 Skia API 将数据绘制到 Surfece
  if (compositor_frame && compositor_frame->Raster(layer_tree, false)) {
    // 绘制结束，提交渲染数据到 GPU 中
    frame->Submit();
    FireNextFrameCallbackIfPresent();
    if (surface_->GetContext())
      surface_->GetContext()->performDeferredCleanup(kSkiaCleanupExpiration);
    return true;
  }

  return false;
}
```

>关于栅格化，来自 [wiki](https://zh.wikipedia.org/wiki/栅格化)
>
>**栅格化**是将[向量图形](https://zh.wikipedia.org/wiki/向量圖形)格式表示的图像转换成[位图](https://zh.wikipedia.org/wiki/點陣圖)以用于[显示器](https://zh.wikipedia.org/wiki/显示器)或者[打印机](https://zh.wikipedia.org/wiki/印表機)输出的过程。
>
>![Rasterizer](http://imgtec.eetrend.com/sites/imgtec.eetrend.com/files/201806/forum/16779-34768-0bj.png)

![OpenGL](https://learnopengl-cn.github.io/img/01/04/pipeline.png)



## Layer Tree

![Layer Tree](http://gityuan.com/img/flutter_gpu/ClassLayer.jpg)





## 总结

在 Flutter 中每一帧的绘制，都先在 Native 层(Android 或 iOS) 注册 VSync 信号的回调，调用到 C++ Engine，这是在 platform 线程进行的，再由 Engine 调用到 Dart 层，在 Dart 层会收集需要绘制的数据，这里包含构建、布局、绘制等操作，这是在 UI 线程进行的。绘制的数据又会交由 Engine 进行栅格化渲染，这里会调用 Skia API 绘制 Surface，Suface 实现有 Skia、OpenGL(默认)、Valkan，具体的绘制逻辑封装在不同 layer tree 里，最后提交给 GPU 进行最终显示，这是在 GPU 线程进行的。

![Frame](https://user-gold-cdn.xitu.io/2019/11/1/16e25f78246ed068?w=1869&h=442&f=png&s=75150)

## Engine 开发

### 源码编译

源码编译环境配置可以参考 [Setting-up-the-Engine-development-environmentn](https://github.com/flutter/flutter/wiki/Setting-up-the-Engine-development-environment)

源码编译可以参考 [Compiling-the-engine](https://github.com/flutter/flutter/wiki/Compiling-the-engine)

源码阅读可以使用 VS Code 和 Android Studio。

C++ 代码的索引、跳转等可以使用 [cquery](https://github.com/cquery-project/cquery)，VS Code 支持它，在编译源码成功后，将 src/out/compile_commands.json 拷贝到 src/flutter 目录下即可。

### Engine 调试

Engine 的调试可以使用 LLDB，可使用 VS Code + CodeLLDB 插件，具体阅读 [Flutter Engine源码调试]([https://xinbaos.github.io/Flutter%20Engine%E6%BA%90%E7%A0%81%E8%B0%83%E8%AF%95](https://xinbaos.github.io/Flutter Engine源码调试))

![LLDB配置](https://user-gold-cdn.xitu.io/2019/11/1/16e25dc91ecd2086?w=999&h=297&f=png&s=57763)

### 使用自定义的 Engine 启动

``` shell
flutter run --local-engine=android_debug_unopt --local-engine-src-path ~/Documents/engine/src
```

