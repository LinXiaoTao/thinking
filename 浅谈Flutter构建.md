### 不同版本构建产物的差异

写这篇文章的时间为：2019.08.25，当前 Flutter SDK 最新版本为 v1.9.5，其中 stable 最新版本为 v1.7.8+hotfix.4。

随着版本的更新，Flutter 构建的产物也在调整，以 Android 为例，我们使用默认的 flutter_app 项目来测试，在不修改源码的情况下，使用不同的 SDK 版本来执行打包命令，每个版本都打两个包：debug 和 release。

![APK](https://user-gold-cdn.xitu.io/2019/8/25/16cc779633694337?w=758&h=506&f=png&s=34431)

每个版本生成的 Flutter 产物如下所示，这里不列出 fonts、LICENSE 这些文件：

| 版本  | 类型    | 内容                                                         | 说明                                                         |
| ----- | ------- | ------------------------------------------------------------ | ------------------------------------------------------------ |
| 1.5.4 | debug   | assets/flutter_assets/kernel_blob.bin<br />assets/flutter_assets/isolate_snapshot_data<br />assets/flutter_assets/vm_snapshot_data<br />lib/x86_64/libflutter.so<br />lib/x86/libflutter.so<br />lib/armeabi-v7a/libflutter.so |                                                              |
| 1.5.4 | release | assets/isolate_snapshot_data<br />assets/isolate_snapshot_instr<br />assets/vm_snapshot_data<br />assets/vm_snapshot_instr<br />lib/armeabi-v7a/libflutter.so |                                                              |
| 1.6.7 | debug   | 新增了<br />assets/snapshot_blob.bind.d.fingerprint<br />assets/snapshot_blob.bin.d<br /> |                                                              |
| 1.6.7 | release | 无变化                                                       |                                                              |
| 1.7.8 | debug   | 删除了<br />assets/snapshot_blob.bind.d.fingerprint<br />assets/snapshot_blob.bin.d<br />新增了<br />lib/arm64-v8a/libflutter.so |                                                              |
| 1.7.8 | release | 删除了<br />assets/isolate_snapshot_data<br />assets/isolate_snapshot_instr<br />assets/vm_snapshot_data<br />assets/vm_snapshot_instr<br />新增了<br />lib/armeabi-v7a/libapp.so<br />lib/arm64-v8a/libflutter.so<br />lib/arm64-v8a/libapp.so | 从这个版本开始，release 下不使用 snapshot，同时增加了同时打包 64 位 so 文件 |
| 1.8.4 | debug   | 无变化                                                       |                                                              |
| 1.8.4 | release | 无变化                                                       |                                                              |
| 1.9.5 | debug   | 无变化                                                       |                                                              |
| 1.9.5 | release | 无变化                                                       |                                                              |

从上面的表格来看，1.5.x 版本和 1.7.x 版本的变化是比较明显的，主要的变化有两点，第一，1.7.x 版本增加了支持同时编译 32 位和 64 位两种架构，这个在之前一直被诟病，现在官方支持了。第二，release 模式下，不使用 snapshot 文件，而使用 libapp.so。snapshot 是 Dart VM 所支持的一种文件格式，类似 JVM 的 jar 一样，可以运行在虚拟机环境的文件。

除了变化以外，我们还注意到一些不变的文件，比如 debug 模式下，一直存在的 kernel_blob.bin 文件；lib 目录下 libflutter.so 文件；这些文件各自的作用又是什么呢。带着疑问，我们一起看看 Flutter 的构建过程。

### Flutter 支持的编译模式

> 关于编译模式这块主要参考的：
>
> * [Flutter’s Compilation Patterns](https://proandroiddev.com/flutters-compilation-patterns-24e139d14177)

Flutter 是基于 Dart 开发的，所以 Flutter 的构建跟 Dart 是分不开的。所以，我们先讲 Dart。

在将 Dart 之前，我们先了解两种编译模式，JIT 和 AOT：

##### JIT

JIT(Just In Time) 翻译为 **即时编译**，指的是在程序运行中，将热点代码编译成机器码，提高运行效率。常见例子有 V8 引擎和 JVM，JIT 可以充分利用解释型语言的优点，动态执行源码，而不用考虑平台差异性。这里需要注意的是，对于 JVM 来说，源码指字节码，而不是 Java 源码。

> 这里需要区分，JIT 和解释型语言的区别，JIT 是一种编译模式，比如，Java 是编译型语言，但它也可以使用 JIT。

##### AOT

AOT(Ahead Of Time) 称为 **运行前编译**，指的是在程序运行之前，已经编译成对应平台的机器码，不需要在运行中解释编译，就可以直接运行。常见例子有 C 和 C++。

虽然，我们会区别 JIT 和 AOT 两种编译模式，但实际上，有很多语言并不是完全使用 JIT 或者 AOT 的，通常它们会混用这两种模式，来达到最大的性能优化。

#### Dart 支持的编译模式

Dart VM 支持四种编译模式：

* **Script**：最常见的 JIT 模式，可以直接在虚拟机中执行 Dart 源码，像解释型语言一样使用。

* **Script Snapshot**：JIT 模式，和 **Script** 模式不同的是，这种模式执行的是 **tokenized code(标记化代码)**，这是经过语法分析后的结果。

  > 关于 语法分析，来自维基百科：
  >
  > **词法分析**（英语：**lexical analysis**）是[计算机科学](https://zh.wikipedia.org/wiki/计算机科学)中将字符序列转换为**标记**（token）序列的过程。进行词法分析的程序或者函数叫作**词法分析器**（lexical analyzer，简称lexer），也叫**扫描器**（scanner）。词法分析器一般以函数的形式存在，供[语法分析器](https://zh.wikipedia.org/wiki/语法分析器)调用。

* **Application Snapshot**：JIT 模式，这里执行的是，从源码中已经解析过的类和函数，所以它会运行起来会更快。但是这不是平台无关，它只能针对 32位 或者 64位 架构运行。

* **AOT**：AOT 模式，在这种模式下，Dart 源码会被提前编译成机器码，来达到最大的运行效率，同样的，它不是平台无关。

可以用下面这张图来总结上面的四种模式：

> 图片来源于 [flutters-compilation-patterns](https://proandroiddev.com/flutters-compilation-patterns-24e139d14177)

![Dart’s compilation patterns](https://user-gold-cdn.xitu.io/2019/8/25/16cc7eb579c05a1d?w=1344&h=386&f=png&s=54640)

#### Flutter 支持的编译模式

Flutter 除了支持 Dart 的四种编译模式以外，它还有自己特有的编译模式：

* **Script**：和 Dart 的 **Script** 模式一样，但 Flutter 并没有使用它
* **Script Snapshot**：和 Dart 的 **Script Snapshot** 模式一样，但 Flutter 并没有使用它
* **Kernel Snapshot**：执行 Dart 字节码，也叫 **Core Snapshot**，这是与平台无关
* **Core JIT**：执行 Dart 代码的二进制格式，应用数据和指令集会被打包成特定的二进制文件，提供给 Dart 运行时加载，实际上，这是一种 AOT 模式
* **AOT**：和 Dart 的 **AOT** 模式一样

#### debug 模式的编译模式

TODO

#### release 模式下的编译模式

TODO

