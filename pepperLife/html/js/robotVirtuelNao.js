const THREE_MODULE = 'three';
const ORBIT_CONTROLS_MODULE = 'three/examples/jsm/controls/OrbitControls.js';
const GLTF_LOADER_MODULE = 'three/examples/jsm/loaders/GLTFLoader.js';
const ROBOT_VIRTUEL_NAO_VERSION = 'nao-idle-20240701';
const NAO_FOOT_CLEARANCE = 0; // alignment derived from actual mesh bounds

const JOINT_CONFIGS = [
  { joint: 'HeadYaw', node: 'HeadYaw_link', axis: [0, 1, 0], neutral: 0, bounds: { min: -2.08, max: 2.08 }, idle: { amplitude: 0.35, speed: 0.6 } },
  { joint: 'HeadPitch', node: 'HeadPitch_link', axis: [1, 0, 0], neutral: 0, bounds: { min: -0.67, max: 0.51 }, idle: { amplitude: 0.22, speed: 0.75, phase: Math.PI / 2, offset: 0.05 } },
  { joint: 'LShoulderPitch', node: 'LShoulderPitch_link', axis: [0, 0, 1], neutral: 1.45, inputOffset: -1.5, bounds: { min: -2.08, max: 2.09 }, idle: { amplitude: 0.4, speed: 0.9, phase: Math.PI } },
  { joint: 'RShoulderPitch', node: 'RShoulderPitch_link', axis: [0, 0, 1], neutral: 1.45, inputOffset: -1.5, bounds: { min: -2.08, max: 2.09 }, idle: { amplitude: 0.4, speed: 0.9, phase: 0 } },
  { joint: 'LShoulderRoll', node: 'LShoulderRoll_link', axis: [0, 0, 1], neutral: 0.1, bounds: { min: -0.31, max: 1.32 }, idle: { amplitude: 0.2, speed: 0.95, phase: Math.PI / 2, offset: 0.05 } },
  { joint: 'RShoulderRoll', node: 'RShoulderRoll_link', axis: [0, 0, 1], neutral: -0.1, bounds: { min: -1.32, max: 0.31 }, idle: { amplitude: 0.2, speed: 0.95, phase: -Math.PI / 2, offset: -0.05 } },
  { joint: 'LElbowYaw', node: 'LElbowYaw_link', axis: [0, 0, 1], neutral: 0, bounds: { min: -2.09, max: 2.09 }, idle: { amplitude: 0.25, speed: 1.15, phase: Math.PI / 3 } },
  { joint: 'RElbowYaw', node: 'RElbowYaw_link', axis: [0, 0, 1], neutral: 0, bounds: { min: -2.09, max: 2.09 }, idle: { amplitude: 0.25, speed: 1.15, phase: -Math.PI / 3 } },
  { joint: 'LElbowRoll', node: 'LElbowRoll_link', axis: [0, 0, 1], neutral: -0.2, bounds: { min: -1.56, max: -0.03 }, idle: { amplitude: 0.3, speed: 1.05, phase: Math.PI / 2 } },
  { joint: 'RElbowRoll', node: 'RElbowRoll_link', axis: [0, 0, 1], neutral: 0.2, bounds: { min: 0.03, max: 1.56 }, idle: { amplitude: 0.3, speed: 1.05, phase: -Math.PI / 2 } },
  { joint: 'LWristYaw', node: 'LWristYaw_link', axis: [0, 0, 1], neutral: 0, bounds: { min: -1.82, max: 1.82 }, idle: { amplitude: 0.18, speed: 1.3, phase: Math.PI / 2 } },
  { joint: 'RWristYaw', node: 'RWristYaw_link', axis: [0, 0, 1], neutral: 0, bounds: { min: -1.82, max: 1.82 }, idle: { amplitude: 0.18, speed: 1.3, phase: -Math.PI / 2 } },
  { joint: 'LHipYawPitch', node: 'LHipYawPitch_link', axis: [0, 0, 1], neutral: 0, bounds: { min: -1.14, max: 0.44 } },
  { joint: 'RHipYawPitch', node: 'RHipYawPitch_link', axis: [0, 0, 1], neutral: 0, bounds: { min: -1.14, max: 0.44 } },
  // Legs (live data only)
  { joint: 'LHipPitch', node: 'LHipPitch_link', axis: [0, 0, 1], neutral: 0, bounds: { min: -1.04, max: 0.79 } },
  { joint: 'RHipPitch', node: 'RHipPitch_link', axis: [0, 0, 1], neutral: 0, bounds: { min: -1.04, max: 0.79 } },
  { joint: 'LKneePitch', node: 'LKneePitch_link', axis: [0, 0, 1], neutral: 0, bounds: { min: 0, max: 2.08 } },
  { joint: 'RKneePitch', node: 'RKneePitch_link', axis: [0, 0, 1], neutral: 0, bounds: { min: 0, max: 2.08 } },
  { joint: 'LAnklePitch', node: 'LAnklePitch_link', axis: [0, 0, 1], neutral: 0, bounds: { min: -1.18, max: 0.93 } },
  { joint: 'RAnklePitch', node: 'RAnklePitch_link', axis: [0, 0, 1], neutral: 0, bounds: { min: -1.18, max: 0.93 } },
];

const NAO_TORSO_PIVOT_ROOTS = ['LHipYawPitch_link', 'RHipYawPitch_link'];
const NAO_TORSO_PIVOT_JOINTS = ['LHipYawPitch', 'RHipYawPitch', 'LHipPitch', 'RHipPitch', 'LHipRoll', 'RHipRoll'];
const NAO_TORSO_SHARED_SCALE = 0.5;
const NAO_GROUND_NODE_NAMES = [
  'LAnkleRoll_link',
  'RAnkleRoll_link',
  'LAnklePitch_link',
  'RAnklePitch_link',
  'LAnkleRoll',
  'RAnkleRoll',
  'LAnklePitch',
  'RAnklePitch',
  'LFoot',
  'RFoot',
];

function isWebGLAvailable() {
  try {
    const canvas = document.createElement('canvas');
    return Boolean(canvas.getContext('webgl') || canvas.getContext('experimental-webgl'));
  } catch (e) {
    return false;
  }
}

function smoothingFactor(speed, delta) {
  const raw = 1 - Math.exp(-Math.max(speed, 0) * delta);
  return Math.min(Math.max(raw, 0), 1);
}

function nowSeconds() {
  if (typeof performance !== 'undefined' && performance.now) {
    return performance.now() / 1000;
  }
  return Date.now() / 1000;
}

export class RobotVirtuelNao {
  constructor(options = {}) {
    const { container, modelUrl = 'modeles3D/nao/nao.glb', jointConfigs = JOINT_CONFIGS } = options;
    this.container = typeof container === 'string' ? document.querySelector(container) : container;
    this.modelUrl = modelUrl;
    this.jointConfigs = jointConfigs;
    this.version = ROBOT_VIRTUEL_NAO_VERSION;
    this.clock = null;
    this.THREE = null;
    this.renderer = null;
    this.scene = null;
    this.camera = null;
    this.controls = null;
    this.loader = null;
    this.modelRoot = null;
    this.torsoPivot = null;
    this.ground = null;
    this.groundPadding = 0;
    this.groundContactInfo = null;
    this.resizeObserver = null;
    this.windowResizeFallback = false;
    this.jointState = new Map();
    this.baseCompensation = null;
    this.pendingAngles = null;
    this.ready = false;
    this.isDisposed = false;
    this.rafId = null;
    this.liveDataTimeout = 1.5;
    this.batteryStatus = null;
    this.debugState = {
      lastGround: null,
      lastTorso: null,
      lastJoints: null,
      lastCommands: null,
      logLevel: 0,
      capturePending: false,
      autoCapture: false,
    };
    this._installDebugInterface();
    this.handleResize = this.handleResize.bind(this);
    this.animate = this.animate.bind(this);
  }

  async init() {
    if (!this.container) {
      console.warn('[RobotVirtuelNao] Aucun conteneur fourni.');
      return;
    }
    this.container.dataset.state = 'loading';
    this.container.dataset.robotVirtuelVersion = this.version;
    this.container.dataset.robotVirtuelKind = 'nao';
    if (!isWebGLAvailable()) {
      this.showFallback('WebGL non disponible');
      return;
    }
    try {
      await this.setupThree();
      await this.loadModel();
      this.start();
    } catch (err) {
      console.error('[RobotVirtuelNao] Échec de l\'initialisation', err);
      this.showFallback('Impossible de charger le modèle NAO');
    }
  }

  async setupThree() {
    const [THREE, controlsModule, loaderModule] = await Promise.all([
      import(THREE_MODULE),
      import(ORBIT_CONTROLS_MODULE),
      import(GLTF_LOADER_MODULE),
    ]);
    if (!THREE || !controlsModule || !loaderModule) {
      throw new Error('Modules Three.js introuvables');
    }
    const OrbitControls = controlsModule.OrbitControls || controlsModule.default;
    const GLTFLoader = loaderModule.GLTFLoader || loaderModule.default;
    if (!OrbitControls || !GLTFLoader) {
      throw new Error('Dépendances Three.js manquantes (OrbitControls/GLTFLoader)');
    }
    this.THREE = THREE;
    this.scratch = this.scratch || {
      box: new THREE.Box3(),
      vector: new THREE.Vector3(),
    };
    this.clock = new THREE.Clock();
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.setPixelRatio(window.devicePixelRatio || 1);
    this.renderer.setSize(this.container.clientWidth || 1, this.container.clientHeight || 1);
    if ('outputColorSpace' in this.renderer) {
      this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    } else if ('outputEncoding' in this.renderer) {
      this.renderer.outputEncoding = THREE.sRGBEncoding;
    }
    this.scene = new THREE.Scene();
    this.scene.background = null;
    this.camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
    this.camera.position.set(1.4, 1.0, 2.2);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.target.set(0, 0.7, 0);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.update();
    const hemiLight = new THREE.HemisphereLight(0xffffff, 0x1b2435, 0.92);
    this.scene.add(hemiLight);
    const dirLight = new THREE.DirectionalLight(0xffffff, 0.85);
    dirLight.position.set(2.3, 3.0, 1.4);
    this.scene.add(dirLight);
    const textureLoader = new THREE.TextureLoader();
    const groundTexture = textureLoader.load('modeles3D/sol.jpg', undefined, undefined, () => {
      console.warn('[RobotVirtuelNao] Texture de sol indisponible, utilisation d\'un matériau neutre.');
    });
    if (groundTexture) {
      if ('colorSpace' in groundTexture) {
        groundTexture.colorSpace = THREE.SRGBColorSpace;
      } else if ('encoding' in groundTexture) {
        groundTexture.encoding = THREE.sRGBEncoding;
      }
      groundTexture.wrapS = THREE.RepeatWrapping;
      groundTexture.wrapT = THREE.RepeatWrapping;
      groundTexture.repeat.set(3, 3);
      if (this.renderer && this.renderer.capabilities && typeof this.renderer.capabilities.getMaxAnisotropy === 'function') {
        groundTexture.anisotropy = this.renderer.capabilities.getMaxAnisotropy();
      }
    }
    const groundMaterial = new THREE.MeshStandardMaterial({
      map: groundTexture || null,
      color: groundTexture ? 0xffffff : 0x152032,
      roughness: 0.92,
      metalness: 0.05,
    });
    if (!groundTexture) {
      groundMaterial.opacity = 0.68;
      groundMaterial.transparent = true;
    }
    this.ground = new THREE.Mesh(new THREE.CircleGeometry(1.65, 60), groundMaterial);
    this.ground.rotation.x = -Math.PI / 2;
    this.ground.position.y = 0;
    this.scene.add(this.ground);
    this.container.innerHTML = '';
    this.container.appendChild(this.renderer.domElement);
    this.loader = new GLTFLoader();
    this.startResizeObserver();
    this.handleResize();
  }

  async loadModel() {
    if (!this.loader) {
      throw new Error('GLTFLoader non initialisé');
    }
    await new Promise((resolve, reject) => {
      this.loader.load(
        this.modelUrl,
        (gltf) => {
          try {
            if (this.isDisposed || !this.scene) {
              resolve();
              return;
            }
            this._configureModel(gltf);
            resolve();
          } catch (err) {
            reject(err);
          }
        },
        undefined,
        (err) => reject(err)
      );
    });
    this.ready = true;
    this.container.dataset.state = 'ready';
    if (this.pendingAngles) {
      this.setJointAngles(this.pendingAngles);
      this.pendingAngles = null;
    }
  }

  _configureModel(gltf) {
    const modelGroup = new this.THREE.Group();
    modelGroup.name = 'NAORoot';
    gltf.scene.scale.setScalar(1.3);
    modelGroup.add(gltf.scene);
    this.scene.add(modelGroup);
    this.modelRoot = modelGroup;
    gltf.scene.rotation.set(-Math.PI / 2, 0, 0);
    gltf.scene.updateMatrixWorld(true);
    const bbox = new this.THREE.Box3().setFromObject(gltf.scene);
    const size = bbox.getSize(new this.THREE.Vector3());
    const center = bbox.getCenter(new this.THREE.Vector3());
    gltf.scene.position.sub(center);
    gltf.scene.position.y += size.y * 0.5;
    const focusY = Math.max(size.y * 0.45, 0.6);
    this.controls.target.set(0, focusY, 0);
    let maxDim = Math.max(size.x, size.y, size.z, 0.6);
    const fov = this.camera.fov * (Math.PI / 180);
    modelGroup.rotation.y = -Math.PI / 2;
    let cameraDistance = (maxDim / Math.tan(fov / 2)) * 0.85 + 0.1;
    cameraDistance = Math.max(cameraDistance, 0.7);
    const cameraHeight = focusY + Math.max(size.y * 0.2, 0.14);
    this.camera.position.set(0, cameraHeight, cameraDistance);
    this.controls.update();
    this.camera.lookAt(this.controls.target);
    const sceneBounds = new this.THREE.Box3().setFromObject(gltf.scene);
    if (Number.isFinite(sceneBounds.min.y) && Math.abs(sceneBounds.min.y) > 1e-5) {
      const lift = -sceneBounds.min.y;
      gltf.scene.position.y += lift;
      gltf.scene.updateMatrixWorld(true);
      modelGroup.updateMatrixWorld(true);
    }
    const initialBounds = new this.THREE.Box3().setFromObject(modelGroup);
    const initialBaseline = initialBounds.min.y;
    const nodeLookup = new Map();
    gltf.scene.traverse((obj) => {
      if (obj && obj.name && !nodeLookup.has(obj.name)) {
        nodeLookup.set(obj.name, obj);
      }
    });
    this._setupTorsoPivot(nodeLookup);
    this.jointState.clear();
  this.jointConfigs.forEach((cfg) => {
      const node = nodeLookup.get(cfg.node);
      if (!node) {
        return;
      }
      const axis = new this.THREE.Vector3().fromArray(cfg.axis).normalize();
      const controller = {
        joint: cfg.joint,
        object: node,
        bindObject: node,
        initial: node.quaternion.clone(),
        axis,
        bindAxis: axis.clone(),
        neutral: cfg.neutral || 0,
        shift: cfg.inputOffset || 0,
        scale: cfg.inputScale !== undefined ? cfg.inputScale : 1,
        bounds: cfg.bounds || null,
        liveSmoothing: cfg.liveSmoothing || 6.0,
        idleSmoothing: cfg.idleSmoothing || 2.0,
        idle: cfg.idle || null,
        currentAngle: cfg.neutral || 0,
        targetAngle: cfg.neutral || 0,
        hasLiveData: false,
        lastLiveTime: 0,
      };
      if (typeof controller.neutral === 'number') {
        controller.object.quaternion.copy(controller.initial);
        const neutralQuat = new this.THREE.Quaternion().setFromAxisAngle(controller.axis, controller.neutral);
        controller.object.quaternion.multiply(neutralQuat);
      }
      this.jointState.set(cfg.joint, controller);
    });
    this._redirectHipJointsToTorsoPivot();
    this.scene.updateMatrixWorld(true);
    const contactNames = ['LAnkleRoll_link', 'RAnkleRoll_link', 'LAnklePitch_link', 'RAnklePitch_link'];
    const contactNodes = contactNames
      .map((name) => nodeLookup.get(name))
      .filter(Boolean);
    if (!contactNodes.length) {
      console.warn('[RobotVirtuelNao] Impossible de localiser les chevilles pour le recalage au sol. Fallback sur le bounding box global.');
    }
    const contactScratch = new this.THREE.Vector3();
    let baselineY = initialBaseline;
    if (contactNodes.length) {
      let minY = Number.POSITIVE_INFINITY;
      contactNodes.forEach((node) => {
        node.getWorldPosition(contactScratch);
        if (contactScratch.y < minY) {
          minY = contactScratch.y;
        }
      });
      if (Number.isFinite(minY)) {
        baselineY = minY;
      }
    }
    if (!Number.isFinite(baselineY)) {
      baselineY = 0;
    }
    this.baseCompensation = {
      baselineY,
      contactNodes,
      scratchVector: contactScratch,
      box: new this.THREE.Box3(),
    };
    this.updateGroundPlane({
      sceneRoot: gltf.scene,
      nodeNames: NAO_GROUND_NODE_NAMES,
    });
    console.log('[RobotVirtuelNao] Joints initialisés:', Array.from(this.jointState.keys()));
  }

  _installDebugInterface() {
    if (typeof window === 'undefined') return;
    window.robotVirtuelNaoDebug = {
      ping: () => `RobotVirtuelNao v${this.version}`,
      getSnapshot: () => this._snapshotDebug(),
      setLogLevel: (level = 1) => {
        const parsed = Number(level) || 0;
        this.debugState.logLevel = parsed;
        return parsed;
      },
      captureFrame: () => {
        this.debugState.capturePending = true;
        this._captureDebugState(true);
        return this._snapshotDebug();
      },
      enableAutoCapture: (flag = true) => {
        this.debugState.autoCapture = Boolean(flag);
        return this.debugState.autoCapture;
      },
    };
  }

  _setupTorsoPivot(nodeLookup) {
    const torsoNode = nodeLookup.get('Torso_link');
    if (!torsoNode || !torsoNode.parent || !this.THREE) {
      this.torsoPivot = null;
      return;
    }
    const parent = torsoNode.parent;
    const hipRoots = NAO_TORSO_PIVOT_ROOTS
      .map((name) => nodeLookup.get(name))
      .filter(Boolean);
    hipRoots.forEach((hipNode) => {
      parent.attach(hipNode);
    });
    const pivot = new this.THREE.Group();
    pivot.name = 'NaoTorsoPivot';
    parent.add(pivot);
    const hipCenterWorld = new this.THREE.Vector3();
    const scratch = new this.THREE.Vector3();
    if (hipRoots.length) {
      hipRoots.forEach((node) => {
        node.getWorldPosition(scratch);
        hipCenterWorld.add(scratch);
      });
      hipCenterWorld.multiplyScalar(1 / hipRoots.length);
      parent.worldToLocal(hipCenterWorld);
      pivot.position.copy(hipCenterWorld);
    } else {
      pivot.position.copy(torsoNode.position);
    }
    pivot.quaternion.set(0, 0, 0, 1);
    pivot.scale.set(1, 1, 1);
    pivot.updateMatrixWorld(true);
    pivot.attach(torsoNode);
    pivot.updateMatrixWorld(true);
    this.torsoPivot = pivot;
  }

  _redirectHipJointsToTorsoPivot() {
    if (!this.torsoPivot || !NAO_TORSO_PIVOT_JOINTS.length) {
      return;
    }
    const baseInitial = this.torsoPivot.quaternion.clone();
    const pivotWorldQuat = new this.THREE.Quaternion();
    this.torsoPivot.getWorldQuaternion(pivotWorldQuat);
    const pivotWorldQuatInv = pivotWorldQuat.clone().invert();
    const sourceQuat = new this.THREE.Quaternion();
    const worldAxis = new this.THREE.Vector3();
    NAO_TORSO_PIVOT_JOINTS.forEach((jointName) => {
      const state = this.jointState.get(jointName);
      if (!state) return;
      const source = state.bindObject || state.object;
      if (source && source.getWorldQuaternion) {
        source.getWorldQuaternion(sourceQuat);
      } else {
        sourceQuat.copy(pivotWorldQuat);
      }
      const originalAxis = state.bindAxis ? state.bindAxis.clone() : state.axis.clone();
      worldAxis.copy(originalAxis).applyQuaternion(sourceQuat).normalize();
      const pivotAxis = worldAxis.clone().applyQuaternion(pivotWorldQuatInv).normalize();
      state.object = this.torsoPivot;
      state.initial = baseInitial.clone();
      state.axis = pivotAxis;
      const baseScale = typeof state.scale === 'number' ? state.scale : 1;
      state.scale = baseScale * NAO_TORSO_SHARED_SCALE;
    });
  }

  start() {
    if (this.isDisposed) return;
    this.animate();
  }

  animate() {
    if (this.isDisposed) return;
    this.rafId = requestAnimationFrame(this.animate);
    if (this.clock) {
      const delta = this.clock.getDelta();
      const elapsed = this.clock.elapsedTime;
      this.updateJoints(delta, elapsed);
    }
    if (this.controls) {
      this.controls.update();
    }
    if (this.renderer && this.scene && this.camera) {
      this.renderer.render(this.scene, this.camera);
    }
  }

  updateJoints(delta, elapsed) {
    const processedObjects = new WeakSet();
    const scratchQuat = new this.THREE.Quaternion();
    this.jointState.forEach((state) => {
      const obj = state.object;
      if (!obj) return;
      const isLive = state.hasLiveData && elapsed - state.lastLiveTime <= this.liveDataTimeout;
      let target = state.targetAngle;
      if (!isLive) {
        state.hasLiveData = false;
        if (state.idle) {
          const { amplitude = 0, speed = 1, phase = 0, offset = 0, invert = false, clamp = null } = state.idle;
          let wave = amplitude ? Math.sin(elapsed * speed + phase) * amplitude : 0;
          if (invert) wave *= -1;
          if (clamp === 'positive') wave = Math.max(0, wave);
          else if (clamp === 'negative') wave = Math.min(0, wave);
          target = state.neutral + offset + wave;
        } else {
          target = state.neutral;
        }
      }
      if (state.bounds && typeof target === 'number') {
        const { min, max } = state.bounds;
        if (min !== undefined) target = Math.max(min, target);
        if (max !== undefined) target = Math.min(max, target);
      }
      const blend = smoothingFactor(isLive ? state.liveSmoothing : state.idleSmoothing, delta);
      state.currentAngle += (target - state.currentAngle) * blend;
      if (!processedObjects.has(obj)) {
        obj.quaternion.copy(state.initial);
        processedObjects.add(obj);
      }
      scratchQuat.setFromAxisAngle(state.axis, state.currentAngle);
      obj.quaternion.multiply(scratchQuat);
    });
    this.applyBaseCompensation();
    this._captureDebugState();
  }

  setJointAngles(angles = {}) {
    const timestamp = nowSeconds();
    if (!this.ready || this.isDisposed) {
      this.pendingAngles = { ...angles };
      return;
    }
    const recorded = Object.assign({}, this.debugState.lastCommands || {});
    Object.entries(angles).forEach(([joint, value]) => {
      const state = this.jointState.get(joint);
      if (!state) return;
      let angle = value;
      if (value && typeof value === 'object') {
        angle = value.angle;
      }
      if (typeof angle !== 'number' || !isFinite(angle)) return;
      let target = state.neutral + (angle + state.shift) * state.scale;
      if (state.bounds) {
        const { min, max } = state.bounds;
        if (min !== undefined) target = Math.max(min, target);
        if (max !== undefined) target = Math.min(max, target);
      }
      state.targetAngle = target;
      state.hasLiveData = true;
      state.lastLiveTime = timestamp;
      recorded[joint] = angle;
    });
    this.debugState.lastCommands = recorded;
  }

  updateBatteryStatus(status) {
    this.batteryStatus = status;
  }

  applyBaseCompensation() {
    if (!this.baseCompensation || !this.modelRoot) return;
    const { baselineY, contactNodes, scratchVector, box } = this.baseCompensation;
    if (!Number.isFinite(baselineY)) return;
    let contactMin = Number.POSITIVE_INFINITY;
    if (contactNodes && contactNodes.length) {
      this.modelRoot.updateMatrixWorld(true);
      contactNodes.forEach((node) => {
        if (!node) return;
        node.getWorldPosition(scratchVector);
        if (scratchVector.y < contactMin) {
          contactMin = scratchVector.y;
        }
      });
    }
    if (!Number.isFinite(contactMin) && box) {
      box.setFromObject(this.modelRoot);
      contactMin = box.min.y;
    }
    if (!Number.isFinite(contactMin)) return;
    const delta = contactMin - baselineY;
    if (Math.abs(delta) <= 1e-4) return;
    const clamped = Math.max(-0.3, Math.min(0.3, delta));
    this.modelRoot.position.y -= clamped;
    this.modelRoot.updateMatrixWorld(true);
    this.debugState.lastGround = {
      baselineY,
      contactMin,
      delta,
      applied: clamped,
      timestamp: Date.now(),
    };
    this._maybeDebug(2, '[RobotVirtuelNao][ground]', this.debugState.lastGround);
  }

  handleResize() {
    if (!this.renderer || !this.camera || !this.container) return;
    const width = this.container.clientWidth || 1;
    const height = this.container.clientHeight || 1;
    this.renderer.setSize(width, height);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
  }

  startResizeObserver() {
    if (typeof ResizeObserver === 'function' && this.container) {
      this.resizeObserver = new ResizeObserver(this.handleResize);
      this.resizeObserver.observe(this.container);
      this.windowResizeFallback = false;
    } else {
      window.addEventListener('resize', this.handleResize);
      this.windowResizeFallback = true;
    }
  }

  stopResizeObserver() {
    if (this.resizeObserver) {
      this.resizeObserver.disconnect();
      this.resizeObserver = null;
    } else if (this.windowResizeFallback) {
      window.removeEventListener('resize', this.handleResize);
      this.windowResizeFallback = false;
    }
  }

  showFallback(message) {
    if (!this.container) return;
    this.container.dataset.state = 'error';
    this.container.innerHTML = `<div class="robot-virtuel__fallback" data-fallback="true">${message}</div>`;
  }

  dispose() {
    this.isDisposed = true;
    if (this.rafId) {
      cancelAnimationFrame(this.rafId);
      this.rafId = null;
    }
    this.stopResizeObserver();
    if (this.renderer && this.renderer.domElement && this.renderer.domElement.parentNode === this.container) {
      this.container.removeChild(this.renderer.domElement);
    }
    if (this.renderer && typeof this.renderer.dispose === 'function') {
      try { this.renderer.dispose(); } catch (e) { /* ignore */ }
    }
    this.renderer = null;
    this.scene = null;
    this.camera = null;
    this.controls = null;
    this.loader = null;
    this.modelRoot = null;
    this.ground = null;
    this.jointState.clear();
  }

  computeGroundContactY({ sceneRoot, nodeNames = [] }) {
    if (!sceneRoot || !this.THREE || !this.scratch) return null;
    const box = this.scratch.box;
    const vec = this.scratch.vector;
    let minY = Number.POSITIVE_INFINITY;
    let source = null;
    const candidates = [];

    const consider = (object, label) => {
      if (!object) return;
      box.setFromObject(object);
      const y = box.min.y;
      if (!Number.isFinite(y)) return;
      candidates.push({
        label,
        min: y,
        max: box.max.y,
        center: box.getCenter(vec).y,
      });
      if (y < minY) {
        minY = y;
        source = label;
      }
    };

    nodeNames
      .map((name) => sceneRoot.getObjectByName(name))
      .filter(Boolean)
      .forEach((node) => consider(node, node.name || 'node'));

    if (!Number.isFinite(minY)) {
      return null;
    }
    return { minY, source, candidates };
  }

  updateGroundPlane({ sceneRoot, nodeNames = [] }) {
    if (!this.ground || !sceneRoot) return;
    const contact = this.computeGroundContactY({ sceneRoot, nodeNames });
    if (!contact) {
      this._maybeDebug(1, '[RobotVirtuelNao] Aucun contact sol détecté', nodeNames);
      return;
    }
    const padding = typeof this.groundPadding === 'number' ? this.groundPadding : 0;
    const targetY = contact.minY + padding;
    const delta = targetY - this.ground.position.y;
    if (Math.abs(delta) <= 1e-4) {
      return;
    }
    this.ground.position.y = targetY;
    this.ground.updateMatrixWorld(true);
    this.groundContactInfo = { ...contact, targetY, padding, delta };
  }

  _captureDebugState(force = false) {
    if (!this.THREE) return;
    const dbg = this.debugState;
    if (
      !force
      && !dbg.autoCapture
      && !dbg.capturePending
      && dbg.logLevel < 3
    ) {
      return;
    }
    dbg.capturePending = false;
    if (this.torsoPivot) {
      if (!this._debugScratch) {
        this._debugScratch = {
          pos: new this.THREE.Vector3(),
          euler: new this.THREE.Euler(),
        };
      }
      const { pos, euler } = this._debugScratch;
      this.torsoPivot.getWorldPosition(pos);
      euler.setFromQuaternion(this.torsoPivot.quaternion, 'XYZ');
      dbg.lastTorso = {
        position: { x: pos.x, y: pos.y, z: pos.z },
        euler: { x: euler.x, y: euler.y, z: euler.z },
        quaternion: this.torsoPivot.quaternion.toArray(),
        timestamp: Date.now(),
      };
    }
    dbg.lastJoints = this._sampleJointAngles([
      'LHipYawPitch',
      'RHipYawPitch',
      'LHipPitch',
      'RHipPitch',
      'LHipRoll',
      'RHipRoll',
      'LKneePitch',
      'RKneePitch',
    ]);
  }

  _sampleJointAngles(names = []) {
    const sample = {};
    names.forEach((joint) => {
      const state = this.jointState.get(joint);
      if (!state) return;
      sample[joint] = {
        current: state.currentAngle,
        target: state.targetAngle,
        neutral: state.neutral,
      };
    });
    return sample;
  }

  _snapshotDebug() {
    return {
      version: this.version,
      ready: this.ready,
      ground: this.debugState.lastGround,
      torso: this.debugState.lastTorso,
      joints: this.debugState.lastJoints,
      commands: this.debugState.lastCommands,
      timestamp: Date.now(),
    };
  }

  _maybeDebug(level, ...args) {
    if (!this.debugState || this.debugState.logLevel < level) return;
    // eslint-disable-next-line no-console
    console.debug(...args);
  }
}
