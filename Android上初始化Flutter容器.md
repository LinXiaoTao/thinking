

### startInitialization

初始化 Flutter 引擎，这个步骤可以在 Application 初始化的时候提前进行，可以减少创建 Flutter 容器的时间，这个步骤包括三个阶段：initConfig、initAot、initResources，最后会加载 flutter so 文件。

#### initConfig

从 metaData 中获取产物名称，metaData 即我们配置在 AndroidManifest.xml 中 <meta-data> 标签中的数据。这里获取的 "app.so"、"vm_snapshot_data"、"vm_snapshot_instr" 等，所以如果我们修改这些默认名称，可以在 AndroidManifest 中配置新的名称。

#### initAot

todo

#### initResources

ResourceExtractor

1. checkTimestamp

   检查 Flutter 产物的时间戳

2. extractUpdate

   提取更新包

3. extractAPK

   提取 Flutter 产物，将 assets 资源目录下的文件 copy 到 /data/data/包名/app_flutter 目录下，这里不会copy 图片这些资源，只处理 vm_snapshot_data 等资源。

ResourceExtractor 中有个内部类 ExtractTask，它继承于 AsyncTask，在异步中依次执行 checkTimestamp、extractUpdate、extractAPK，最后有必要，会重新生成时间戳文件，以 "res_timestamp-" 开头。

### ensureInitializationComplete

preCompiledAsBlobs

preCompiledAsSharedLibrary

todo

### FlutterView

FlutterView 继承于 SurfaceView，它和 native 层的通信实现放在 FlutterNativeView，这个命名让我想到了 MessageQueue 和 NativeMessageQueue。

这里用到了 Lifecycle，它可以用来监听 Activity 的生命周期，在对应的生命周期中，调用 FlutterView 对应的方法。FlutterView 中会使用 LifecycleChannel 通知到 Flutter 模块中。

在 FlutterView 的构造函数中，定义很多的 Channel，包括 NavigationChannel、LifecycleChannel、LocalizationChannel、PlatformChannel 等。它们大部分是用来转发原生上的各种事件到 Flutter 模块中去的，也是注册接受从 Flutter 发送过的消息。

FlutterView 提供了很多公开的 API 给开发者使用，但它的实现是主要是由 MethodChannel，FlutterNativeView 和 DartExecutor 去完成的。

MethodChannel 依赖于 BinaryMessenger，BinaryMessenger 的实际实现类其实是 DartMessenger。

而 FlutterNativeView 也是个空壳类，它提供了 API，实现则交给了 FlutterJNI 和 DartExecutor。DartExecutor 也依赖于 FlutterJNI 和 DartMessenger 的实现。DartMessenger 则依赖于 FlutterJNI 的实现。

绕来绕去，虽然类很多，但核心都在 FlutterJNI，它是 Java 层和 Flutter 层的桥梁。

