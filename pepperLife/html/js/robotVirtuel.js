const THREE_MODULE = 'three';
const ORBIT_CONTROLS_MODULE = 'three/examples/jsm/controls/OrbitControls.js';
const GLTF_LOADER_MODULE = 'three/examples/jsm/loaders/GLTFLoader.js';
const ROBOT_VIRTUEL_VERSION = 'hud-battery-20240610-01';
const MODEL_GROUND_OFFSET = 0.07; // lifts Pepper to compensate for wheel geometry offset
const GROUND_EXTRA_CLEARANCE = 0.015;
const DEFAULT_GROUND_PADDING = -MODEL_GROUND_OFFSET - GROUND_EXTRA_CLEARANCE;
const BATTERY_HUD_ALIGNMENT = {
  position: { x: 0, y: -0.013, z: 0.038 },
  rotation: {
    x: 0,
    y: Math.PI / 1.5,
    z: Math.PI / 2,
  },
};
const JOINT_MAPPINGS = [
  { joint: 'HipPitch', node: 'PepperUpperBody', axis: [0, 1, 0], neutral: 0, bounds: { min: -1.0, max: 1.0 }, inputScale: -1 },
  { joint: 'HipRoll', node: 'PepperUpperBody', axis: [1, 0, 0], neutral: 0, bounds: { min: -0.8, max: 0.8 }, inputScale: -1 },
  { joint: 'KneePitch', node: 'PepperAboveKnee', axis: [0, 1, 0], neutral: 0, bounds: { min: -0.514872, max: 0.514872 }, inputScale: -1 },
  { joint: 'HeadYaw', node: 'HeadYaw_link', axis: [0, 0, 1], neutral: 0 },
  { joint: 'HeadPitch', node: 'HeadPitch_link', axis: [0, 0, 1], neutral: 0 },
  { joint: 'LShoulderPitch', node: 'LShoulderPitch_link', axis: [0, 0, 1], neutral: 1.5, inputOffset: -1.5 },
  { joint: 'RShoulderPitch', node: 'RShoulderPitch_link', axis: [0, 0, 1], neutral: 1.5, inputOffset: -1.5 },
  { joint: 'LShoulderRoll', node: 'LShoulderRoll_link', axis: [0, 0, 1], neutral: 0, bounds: { min: -1.0, max: 1.0 } },
  { joint: 'RShoulderRoll', node: 'RShoulderRoll_link', axis: [0, 0, 1], neutral: 0, bounds: { min: -1.0, max: 1.0 } },
  { joint: 'LElbowYaw', node: 'LElbowYaw_link', axis: [0, 0, 1], neutral: 0, bounds: { min: -2.09, max: 2.09 } },
  { joint: 'RElbowYaw', node: 'RElbowYaw_link', axis: [0, 0, 1], neutral: 0, bounds: { min: -2.09, max: 2.09 } },
  { joint: 'LElbowRoll', node: 'LElbowRoll_link', axis: [0, 0, 1], neutral: 0, bounds: { min: -1.56, max: 0 } },
  { joint: 'RElbowRoll', node: 'RElbowRoll_link', axis: [0, 0, 1], neutral: 0, bounds: { min: 0, max: 1.56207 } },
  { joint: 'LWristYaw', node: 'LWristYaw_link', axis: [0, 0, 1], neutral: 0, inputScale: -1, bounds: { min: -1.82, max: 1.82 } },
  { joint: 'RWristYaw', node: 'RWristYaw_link', axis: [0, 0, 1], neutral: 0, bounds: { min: -1.82, max: 1.82 } },
];

const BASE_NODE_NAMES = [
  'AccelerometerBase',
  'Battery',
  'Bumper/Back',
  'Bumper/FrontLeft',
  'Bumper/FrontRight',
  'DeadAngle/Left',
  'DeadAngle/Right',
  'GyrometerBaseX',
  'GyrometerBaseY',
  'GyrometerBaseZ',
  'LaserSensor/Front',
  'LaserSensor/Left',
  'LaserSensor/Right',
  'LaserSensor/Shovel',
  'LaserSensor/VerticalLeft',
  'LaserSensor/VerticalRight',
  'PowerHatch',
  'Sonar/Back',
  'Sonar/Front',
  'KneePitch',
  'KneePitch_link_visual_0',
  'Leg',
  'WheelB_link',
  'WheelFL_link',
  'WheelFR_link',
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
export class RobotVirtuel {
  constructor(options = {}) {
    const { container, modelUrl = 'modeles3D/pepper/pepper.glb' } = options;
    this.container = typeof container === 'string' ? document.querySelector(container) : container;
    this.modelUrl = modelUrl;
    this.version = ROBOT_VIRTUEL_VERSION;
    this.clock = null;
    this.THREE = null;
    this.renderer = null;
    this.scene = null;
    this.camera = null;
    this.controls = null;
    this.resizeObserver = null;
    this.rafId = null;
    this.loader = null;
    this.modelRoot = null;
    this.ready = false;
    this.isDisposed = false;
    this.pivots = { upperPitch: null, upperRoll: null, knee: null };
    this.baseCompensation = null;
    this.scratch = null;
    this.jointState = new Map();
    this.pendingAngles = null;
    this.liveDataTimeout = 1.6;
    this.batteryStatus = null;
    this.batteryHUD = {
      panel: null,
      material: null,
      texture: null,
      canvas: null,
      ctx: null,
      lastKey: null,
      tabletNode: null,
    };
    this.handleResize = this.handleResize.bind(this);
    this.animate = this.animate.bind(this);
  }
  async init() {
    if (!this.container) {
      console.warn('[RobotVirtuel] Aucun conteneur fourni.');
      return;
    }
    this.container.dataset.state = 'loading';
    this.container.dataset.robotVirtuelVersion = this.version;
    if (!isWebGLAvailable()) {
      this.showFallback('WebGL non disponible');
      return;
    }
    try {
      await this.setupThree();
      await this.loadModel();
      this.start();
    } catch (err) {
      console.error('[RobotVirtuel] Échec du chargement du modèle 3D', err);
      this.showFallback('Impossible de charger le modèle 3D');
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
    this.THREE = THREE;
    const OrbitControls = controlsModule.OrbitControls || controlsModule.default;
    const GLTFLoader = loaderModule.GLTFLoader || loaderModule.default;
    if (!OrbitControls || !GLTFLoader) {
      throw new Error('Dépendances Three.js manquantes (OrbitControls/GLTFLoader)');
    }
    this.scratch = {
      matrix: new THREE.Matrix4(),
      quatA: new THREE.Quaternion(),
      quatB: new THREE.Quaternion(),
      vector: new THREE.Vector3(),
      scale: new THREE.Vector3(),
      box: new THREE.Box3(),
    };
    this.loader = new GLTFLoader();
    this.clock = new THREE.Clock();
    this.scene = new THREE.Scene();
    this.scene.background = null;
    this.camera = new THREE.PerspectiveCamera(
      40,
      this.container.clientWidth / Math.max(this.container.clientHeight, 1),
      0.1,
      100,
    );
    this.camera.position.set(1.7, 1.1, 2.2);
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.setPixelRatio(window.devicePixelRatio || 1);
    this.renderer.setSize(this.container.clientWidth, Math.max(this.container.clientHeight, 1));
    if ('outputColorSpace' in this.renderer) {
      this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    } else if ('outputEncoding' in this.renderer) {
      this.renderer.outputEncoding = THREE.sRGBEncoding;
    }
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.enablePan = false;
    this.controls.minDistance = 1.0;
    this.controls.maxDistance = 3.8;
    this.controls.target.set(-0.08, 0.95, 0.0);
    this.controls.update();
    const hemiLight = new THREE.HemisphereLight(0xffffff, 0x1b2636, 0.85);
    this.scene.add(hemiLight);
    const dirLight = new THREE.DirectionalLight(0xffffff, 0.9);
    dirLight.position.set(2.5, 3.0, 1.2);
    this.scene.add(dirLight);
    this.modelGroundOffset = MODEL_GROUND_OFFSET;
    this.groundPadding = DEFAULT_GROUND_PADDING;
    this.groundContactInfo = null;
    const textureLoader = new THREE.TextureLoader();
    const groundTexture = textureLoader.load('modeles3D/sol.jpg', undefined, undefined, () => {
      console.warn('[RobotVirtuel] Échec du chargement de la texture de sol, retour au matériau neutre.');
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

    const ground = new THREE.Mesh(new THREE.CircleGeometry(1.8, 60), groundMaterial);
    ground.rotation.x = -Math.PI / 2;
    ground.position.y = 0;
    this.scene.add(ground);
    this.ground = ground;
    this.container.innerHTML = '';
    this.container.appendChild(this.renderer.domElement);
    this.resizeObserver = new ResizeObserver(this.handleResize);
    this.resizeObserver.observe(this.container);
  }
  async loadModel() {
    this.baseCompensation = null;
    const nodeLookup = new Map();
    JOINT_MAPPINGS.forEach((cfg) => {
      if (!nodeLookup.has(cfg.node)) {
        nodeLookup.set(cfg.node, []);
      }
      nodeLookup.get(cfg.node).push(cfg);
    });
    await new Promise((resolve, reject) => {
      this.loader.load(
        this.modelUrl,
        (gltf) => {
          gltf.scene.position.set(0, 0, 0);
          gltf.scene.scale.setScalar(1.25);
          const group = new this.THREE.Group();
          group.name = 'RobotVirtuelRoot';
          group.add(gltf.scene);
          const orientationFix = new this.THREE.Euler(-Math.PI / 2, 0, 0, 'XYZ');
          gltf.scene.rotation.copy(orientationFix);
          this.scene.add(group);
          this.modelRoot = group;
          const box = new this.THREE.Box3().setFromObject(group);
          const size = box.getSize(new this.THREE.Vector3());
          const center = box.getCenter(new this.THREE.Vector3());
          gltf.scene.position.sub(center);
          gltf.scene.position.y += size.y / 2;
          const yawFacingCamera = -Math.PI / 2;
          group.rotation.y = yawFacingCamera;
          const focusY = Math.max(size.y * 0.48, 0.8);
          this.controls.target.set(0, focusY, 0);
          let maxDim = Math.max(size.x, size.z, size.y);
          if (!isFinite(maxDim) || maxDim <= 0) {
            maxDim = 1.2;
          }
          const halfMax = maxDim / 2;
          const fov = this.camera.fov * (Math.PI / 180);
          let cameraDistance = halfMax / Math.tan(fov / 2);
          cameraDistance = cameraDistance * 1.05 + 0.15;
          this.controls.minDistance = Math.max(maxDim * 0.5, 0.7);
          this.controls.maxDistance = Math.max(maxDim * 3.8, this.controls.minDistance + 1.2);
          cameraDistance = Math.max(cameraDistance, this.controls.minDistance + 0.2);
          const cameraHeight = focusY + Math.max(size.y * 0.18, 0.12);
          this.camera.position.set(0, cameraHeight, cameraDistance);
          this.controls.update();
          this.camera.lookAt(this.controls.target);
          this.scene.updateMatrixWorld(true);
          const sceneBounds = new this.THREE.Box3().setFromObject(gltf.scene);
          if (Number.isFinite(sceneBounds.min.y) && Math.abs(sceneBounds.min.y) > 1e-5) {
            const lift = -sceneBounds.min.y;
            gltf.scene.position.y += lift;
            gltf.scene.updateMatrixWorld(true);
            this.scene.updateMatrixWorld(true);
          }
          if (typeof this.modelGroundOffset === 'number' && Math.abs(this.modelGroundOffset) > 1e-6) {
            gltf.scene.position.y += this.modelGroundOffset;
            gltf.scene.updateMatrixWorld(true);
            this.scene.updateMatrixWorld(true);
          }
          let baseCompensation = null;
          const findNode = (name) => gltf.scene.getObjectByName(name);
          const kneeNode = findNode('KneePitch_link');
          const aboveKneeNode = findNode('PepperAboveKnee');
          const upperBodyNode = findNode('PepperUpperBody');
          const createdPivots = {
            upperPitch: null,
            upperRoll: null,
            upper: null,
            knee: null,
          };
          if (upperBodyNode) {
            const upperParent = upperBodyNode.parent;
            const rollPivot = new this.THREE.Group();
            rollPivot.name = 'PepperUpperBodyRollPivot';
            const pitchPivot = new this.THREE.Group();
            pitchPivot.name = 'PepperUpperBodyPitchPivot';
            const originalPos = upperBodyNode.position.clone();
            const originalQuat = upperBodyNode.quaternion.clone();
            const originalScale = upperBodyNode.scale.clone();
            rollPivot.position.set(0, 0, 0);
            pitchPivot.position.set(0, 0, 0);
            upperParent.add(rollPivot);
            rollPivot.add(pitchPivot);
            pitchPivot.add(upperBodyNode);
            upperBodyNode.position.copy(originalPos);
            upperBodyNode.quaternion.copy(originalQuat);
            upperBodyNode.scale.copy(originalScale);
            rollPivot.updateMatrixWorld(true);
            pitchPivot.updateMatrixWorld(true);
            upperBodyNode.updateMatrixWorld(true);
            createdPivots.upperRoll = rollPivot;
            createdPivots.upperPitch = pitchPivot;
            createdPivots.upper = pitchPivot;
          }
          if (kneeNode && aboveKneeNode && createdPivots.upper) {
            const kneePivot = new this.THREE.Group();
            kneePivot.name = 'PepperKneePivot';
            const torsoNode = findNode('Torso_link') || aboveKneeNode.parent;
            torsoNode.add(kneePivot);
            const kneeWorldPos = new this.THREE.Vector3();
            kneeNode.getWorldPosition(kneeWorldPos);
            torsoNode.worldToLocal(kneeWorldPos);
            kneePivot.position.copy(kneeWorldPos);
            kneePivot.attach(aboveKneeNode);
            kneePivot.updateMatrixWorld(true);
            aboveKneeNode.updateMatrixWorld(true);
            createdPivots.knee = kneePivot;
          }
          this.scene.updateMatrixWorld(true);
          if (kneeNode) {
            const baseHelper = new this.THREE.Group();
            baseHelper.name = 'PepperBaseHelper';
            kneeNode.add(baseHelper);
            const baseNodes = BASE_NODE_NAMES.map(findNode).filter(Boolean);
            baseNodes.forEach((node) => baseHelper.attach(node));
            this.scene.updateMatrixWorld(true);
            baseHelper.updateMatrixWorld(true);
            const baseBox = this.scratch.box;
            const wheelNodes = [
              'WheelB_link_visual_0',
              'WheelFL_link_visual_0',
              'WheelFR_link_visual_0',
            ]
              .map(findNode)
              .filter(Boolean);
            let offsetY = Number.POSITIVE_INFINITY;
            wheelNodes.forEach((node) => {
              baseBox.setFromObject(node);
              const y = baseBox.min.y;
              if (Number.isFinite(y)) {
                offsetY = Math.min(offsetY, y);
              }
            });
            if (!Number.isFinite(offsetY)) {
              baseBox.setFromObject(baseHelper);
              offsetY = baseBox.min.y;
            }
            if (Number.isFinite(offsetY) && Math.abs(offsetY) > 1e-6) {
              baseHelper.position.y -= offsetY;
              baseHelper.updateMatrixWorld(true);
            }
            const worldMatrix = baseHelper.matrixWorld.clone();
            const worldScale = new this.THREE.Vector3();
            const scratchVec = this.scratch.vector;
            const scratchQuat = this.scratch.quatA;
            worldMatrix.decompose(scratchVec, scratchQuat, worldScale);
            baseCompensation = {
              helper: baseHelper,
              knee: kneeNode,
              worldMatrix,
              worldScale,
            };
          }
          this.updateGroundPlane({
            sceneRoot: gltf.scene,
            nodeNames: [
              'WheelB_link_visual_0',
              'WheelFL_link_visual_0',
              'WheelFR_link_visual_0',
              'WheelB_link',
              'WheelFL_link',
              'WheelFR_link',
              'PepperBaseHelper',
            ],
          });
        gltf.scene.traverse((obj) => {
          const cfgList = nodeLookup.get(obj.name);
          if (!cfgList) return;
          cfgList.forEach((cfg) => {
            const axis = new this.THREE.Vector3().fromArray(cfg.axis).normalize();
            const controller = {
              joint: cfg.joint,
              object: obj,
              initial: obj.quaternion.clone(),
              axis,
              scale: cfg.inputScale !== undefined ? cfg.inputScale : 1,
              shift: cfg.inputOffset || 0,
              neutral: cfg.neutral || 0,
              currentAngle: cfg.neutral || 0,
              targetAngle: cfg.neutral || 0,
              hasLiveData: false,
              lastLiveTime: 0,
              liveSmoothing: cfg.liveSmoothing || 6.0,
              idleSmoothing: cfg.idleSmoothing || 2.0,
              bounds: cfg.bounds || null,
            };
            if (typeof controller.neutral === 'number' && controller.object) {
              controller.object.quaternion.copy(controller.initial);
              const neutralQuat = new this.THREE.Quaternion().setFromAxisAngle(controller.axis, controller.neutral);
              controller.object.quaternion.multiply(neutralQuat);
            }
            this.jointState.set(cfg.joint, controller);
          });
        });
          const hipPitchState = this.jointState.get('HipPitch');
          const hipRollState = this.jointState.get('HipRoll');
          const kneeState = this.jointState.get('KneePitch');
          if (createdPivots.upperPitch && hipPitchState) {
            hipPitchState.object = createdPivots.upperPitch;
            hipPitchState.initial = createdPivots.upperPitch.quaternion.clone();
            hipPitchState.axis = new this.THREE.Vector3(0, 1, 0);
          } else {
            console.warn(`[RobotVirtuel v${this.version}] Pivot HipPitch manquant`, {
              hasState: Boolean(hipPitchState),
              hasUpperPitch: Boolean(createdPivots.upperPitch),
            });
          }
          if (createdPivots.upperRoll && hipRollState) {
            hipRollState.object = createdPivots.upperRoll;
            hipRollState.initial = createdPivots.upperRoll.quaternion.clone();
            hipRollState.axis = new this.THREE.Vector3(1, 0, 0);
          } else if (createdPivots.upper && hipRollState) {
            hipRollState.object = createdPivots.upper;
            hipRollState.initial = createdPivots.upper.quaternion.clone();
            hipRollState.axis = new this.THREE.Vector3(1, 0, 0);
            console.warn(`[RobotVirtuel v${this.version}] HipRoll fallback sur pivot upper`, {
              hasUpperRoll: Boolean(createdPivots.upperRoll),
            });
          } else {
            console.warn(`[RobotVirtuel v${this.version}] Pivot HipRoll manquant`, {
              hasState: Boolean(hipRollState),
              hasUpperRoll: Boolean(createdPivots.upperRoll),
            });
          }
          if (createdPivots.knee && kneeState) {
            kneeState.object = createdPivots.knee;
            kneeState.initial = createdPivots.knee.quaternion.clone();
            kneeState.axis = new this.THREE.Vector3(0, 1, 0);
          }
          this.pivots = {
            upperPitch: createdPivots.upperPitch || createdPivots.upper,
            upperRoll: createdPivots.upperRoll || null,
            knee: createdPivots.knee,
          };
          this.setupBatteryHUD(gltf.scene);
          const tabletNode = gltf.scene.getObjectByName('Tablet') || gltf.scene.getObjectByName('Tablet_display');
          this.baseCompensation = baseCompensation;
          this.ready = true;
          this.container.dataset.state = 'ready';
          if (this.pendingAngles) {
            this.setJointAngles(this.pendingAngles);
            this.pendingAngles = null;
          }
          resolve();
        },
        undefined,
        (err) => reject(err),
      );
    });
  }
  start() {
    if (this.isDisposed) return;
    this.animate();
  }
  animate() {
    if (this.isDisposed) return;
    this.rafId = requestAnimationFrame(this.animate);
    if (this.controls) {
      this.controls.update();
    }
    if (this.clock) {
      const delta = this.clock.getDelta();
      const elapsed = this.clock.elapsedTime;
      this.updateJoints(delta, elapsed);
      this.applyBaseCompensation();
    }
    if (this.renderer && this.scene && this.camera) {
      this.renderer.render(this.scene, this.camera);
    }
  }
  applyBaseCompensation() {
    if (!this.baseCompensation || !this.baseCompensation.helper) return;
    const helperParent = this.baseCompensation.helper.parent;
    if (!helperParent) return;
    helperParent.updateMatrixWorld(true);
    const scratchMatrix = this.scratch.matrix;
    const scratchVector = this.scratch.vector;
    const scratchQuat = this.scratch.quatA;
    const scratchScale = this.scratch.scale;
    scratchMatrix.copy(helperParent.matrixWorld).invert().multiply(this.baseCompensation.worldMatrix);
    scratchMatrix.decompose(scratchVector, scratchQuat, scratchScale);
    this.baseCompensation.helper.position.copy(scratchVector);
    this.baseCompensation.helper.quaternion.copy(scratchQuat);
    this.baseCompensation.helper.scale.copy(this.baseCompensation.worldScale);
    this.baseCompensation.helper.updateMatrixWorld(true);
  }
  setupBatteryHUD(sceneRoot) {
    if (!sceneRoot || !this.THREE) {
      console.warn('[RobotVirtuel] setupBatteryHUD ignoré: scène ou THREE manquant');
      return;
    }
    const tabletNode = sceneRoot.getObjectByName('Tablet') || sceneRoot.getObjectByName('Tablet_display');
    if (!tabletNode) {
      console.warn('[RobotVirtuel] Impossible de localiser le noeud Tablet pour le HUD batterie.');
      return;
    }
    this.disposeBatteryHUD();
    const canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 256;
    const ctx = canvas.getContext('2d');
    if (!ctx) {
      console.warn('[RobotVirtuel] Canvas 2D non disponible pour le HUD batterie.');
      return;
    }
    const texture = new this.THREE.CanvasTexture(canvas);
    if ('colorSpace' in texture) {
      texture.colorSpace = this.THREE.SRGBColorSpace;
    } else if ('encoding' in texture) {
      texture.encoding = this.THREE.sRGBEncoding;
    }
    const capabilities = this.renderer ? this.renderer.capabilities : null;
    if (capabilities && typeof capabilities.getMaxAnisotropy === 'function') {
      texture.anisotropy = capabilities.getMaxAnisotropy();
    }
    const material = new this.THREE.MeshBasicMaterial({
      transparent: true,
      map: texture,
      depthTest: false,
      depthWrite: false,
    });
    const panelWidth = 0.18;
    const panelHeight = panelWidth * (canvas.height / canvas.width);
    const geometry = new this.THREE.PlaneGeometry(panelWidth, panelHeight);
    const panel = new this.THREE.Mesh(geometry, material);
    panel.name = 'PepperBatteryHUD';
    const { position, rotation } = BATTERY_HUD_ALIGNMENT;
    panel.position.set(position.x, position.y, position.z);
    panel.renderOrder = 12;
    panel.frustumCulled = false;
    tabletNode.add(panel);
    tabletNode.updateMatrixWorld(true);
    panel.quaternion.copy(tabletNode.quaternion);
    panel.rotateX(rotation.x);
    panel.rotateY(rotation.y);
    panel.rotateZ(rotation.z);
    this.batteryHUD = {
      panel,
      material,
      texture,
      canvas,
      ctx,
      lastKey: null,
      tabletNode,
    };
    this.refreshBatteryHUD(true);
  }
  updateBatteryStatus(batteryData) {
    if (batteryData && typeof batteryData.charge === 'number' && isFinite(batteryData.charge)) {
      const charge = Math.max(0, Math.min(100, batteryData.charge));
      this.batteryStatus = {
        charge,
        plugged: Boolean(batteryData.plugged),
      };
    } else {
      this.batteryStatus = null;
    }
    this.refreshBatteryHUD();
  }
  refreshBatteryHUD(force = false) {
    const hud = this.batteryHUD;
    if (!hud || !hud.ctx || !hud.texture) return;
    const chargeValue =
      this.batteryStatus && typeof this.batteryStatus.charge === 'number'
        ? Math.round(this.batteryStatus.charge)
        : null;
    const plugged = Boolean(this.batteryStatus && this.batteryStatus.plugged);
    let level = 'unknown';
    if (chargeValue !== null) {
      if (chargeValue < 20) level = 'critical';
      else if (chargeValue <= 50) level = 'medium';
      else level = 'high';
    }
    const key = `${chargeValue ?? 'na'}|${plugged ? 1 : 0}|${level}`;
    if (!force && hud.lastKey === key) {
      return;
    }
    hud.lastKey = key;
    const { canvas, ctx, texture } = hud;
    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);

    const padding = Math.round(width * 0.08);
    const corner = Math.round(width * 0.08);
    const bodyX = padding;
    const bodyY = padding;
    const bodyW = width - padding * 2;
    const bodyH = height - padding * 2;

    const iconColorMap = {
      high: '#22c55e',
      medium: '#facc15',
      critical: '#ef4444',
      unknown: '#94a3b8',
    };
    const textColorMap = {
      high: '#15803d',
      medium: '#92400e',
      critical: '#991b1b',
      unknown: '#e2e8f0',
    };
    const iconColor = iconColorMap[level] || iconColorMap.unknown;
    const textColor = textColorMap[level] || textColorMap.unknown;

    const drawRoundedRect = (x, y, w, h, r) => {
      const radius = Math.min(r, h / 2, w / 2);
      ctx.beginPath();
      ctx.moveTo(x + radius, y);
      ctx.lineTo(x + w - radius, y);
      ctx.quadraticCurveTo(x + w, y, x + w, y + radius);
      ctx.lineTo(x + w, y + h - radius);
      ctx.quadraticCurveTo(x + w, y + h, x + w - radius, y + h);
      ctx.lineTo(x + radius, y + h);
      ctx.quadraticCurveTo(x, y + h, x, y + h - radius);
      ctx.lineTo(x, y + radius);
      ctx.quadraticCurveTo(x, y, x + radius, y);
      ctx.closePath();
    };

    drawRoundedRect(bodyX, bodyY, bodyW, bodyH, corner);
    ctx.fillStyle = 'rgba(15,23,42,0.82)';
    ctx.fill();

    const iconPadding = Math.round(width * 0.04);
    const iconWidth = Math.round(bodyW * 0.32);
    const iconHeight = Math.round(bodyH * 0.6);
    const iconX = bodyX + iconPadding;
    const iconY = bodyY + (bodyH - iconHeight) / 2;
    const tipWidth = Math.max(6, Math.round(iconWidth * 0.12));
    const innerPadding = Math.max(4, Math.round(iconWidth * 0.1));
    ctx.lineWidth = Math.max(2, Math.round(width * 0.01));
    ctx.strokeStyle = iconColor;
    ctx.fillStyle = 'rgba(15,23,42,0.18)';

    // Battery outline
    ctx.beginPath();
    ctx.moveTo(iconX, iconY);
    ctx.lineTo(iconX + iconWidth - tipWidth, iconY);
    ctx.lineTo(iconX + iconWidth - tipWidth, iconY + iconHeight * 0.25);
    ctx.lineTo(iconX + iconWidth, iconY + iconHeight * 0.25);
    ctx.lineTo(iconX + iconWidth, iconY + iconHeight * 0.75);
    ctx.lineTo(iconX + iconWidth - tipWidth, iconY + iconHeight * 0.75);
    ctx.lineTo(iconX + iconWidth - tipWidth, iconY + iconHeight);
    ctx.lineTo(iconX, iconY + iconHeight);
    ctx.closePath();
    ctx.stroke();

    // Battery fill
    const fillWidth = chargeValue === null
      ? 0
      : Math.max(
          0,
          Math.min(1, chargeValue / 100),
        ) * (iconWidth - tipWidth - innerPadding * 2);
    if (chargeValue !== null && fillWidth > 0) {
      const fillX = iconX + innerPadding;
      const fillY = iconY + innerPadding;
      const fillH = iconHeight - innerPadding * 2;
      ctx.fillStyle = iconColor;
      ctx.fillRect(fillX, fillY, fillWidth, fillH);
    } else if (chargeValue === null) {
      ctx.strokeStyle = '#e2e8f0';
      ctx.setLineDash([10, 6]);
      ctx.beginPath();
      ctx.moveTo(iconX + innerPadding, iconY + iconHeight / 2);
      ctx.lineTo(iconX + iconWidth - innerPadding - tipWidth, iconY + iconHeight / 2);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // Charging symbol
    if (plugged) {
      const boltWidth = iconWidth * 0.32;
      const boltHeight = iconHeight * 0.5;
      const boltX = iconX + iconWidth / 2 - boltWidth / 2 - tipWidth * 0.25;
      const boltY = iconY + iconHeight / 2 - boltHeight / 2;
      ctx.fillStyle = chargeValue !== null ? '#0f172a' : '#1e293b';
      ctx.beginPath();
      ctx.moveTo(boltX + boltWidth * 0.5, boltY);
      ctx.lineTo(boltX + boltWidth * 0.3, boltY + boltHeight * 0.42);
      ctx.lineTo(boltX + boltWidth * 0.58, boltY + boltHeight * 0.42);
      ctx.lineTo(boltX + boltWidth * 0.5, boltY + boltHeight);
      ctx.lineTo(boltX + boltWidth * 0.7, boltY + boltHeight * 0.56);
      ctx.lineTo(boltX + boltWidth * 0.42, boltY + boltHeight * 0.56);
      ctx.closePath();
      ctx.fill();
    }

    // Percentage text
    const text = chargeValue !== null ? `${chargeValue}%` : '--%';
    ctx.font = `${Math.round(bodyH * 0.46)}px "Inter", "Segoe UI", "Roboto", sans-serif`;
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    ctx.fillStyle = iconColor;
    ctx.fillText(text, bodyX + bodyW - iconPadding, bodyY + bodyH / 2);

    texture.needsUpdate = true;
  }
  disposeBatteryHUD() {
    const hud = this.batteryHUD;
    if (!hud) return;
    if (hud.panel && hud.panel.parent) {
      hud.panel.parent.remove(hud.panel);
    }
    if (hud.texture) {
      hud.texture.dispose();
    }
    if (hud.material) {
      hud.material.dispose();
    }
    if (hud.panel && hud.panel.geometry) {
      hud.panel.geometry.dispose();
    }
    this.batteryHUD = {
      panel: null,
      material: null,
      texture: null,
      canvas: null,
      ctx: null,
      lastKey: null,
      tabletNode: null,
    };
  }
  computeGroundContactY({ sceneRoot, nodeNames = [] }) {
    if (!sceneRoot || !this.scratch || !this.THREE) return null;
    const box = this.scratch.box || new this.THREE.Box3();
    let minY = Number.POSITIVE_INFINITY;
    let source = null;
    const candidates = [];

    const consider = (object, label) => {
      if (!object) return;
      box.setFromObject(object);
      const y = box.min.y;
      if (!Number.isFinite(y)) return;
      const entry = {
        label,
        min: y,
        max: box.max.y,
        center: box.getCenter(new this.THREE.Vector3()).y,
      };
      candidates.push(entry);
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
      console.warn(`[RobotVirtuel v${this.version}] Aucun point bas trouvé pour aligner le sol.`, {
        nodeNames,
      });
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
    // Ground contact re-computed implicitly next update if required.
  }
  updateJoints(delta, elapsed) {
    const processedObjects = new WeakSet();
    const scratchQuat = this.scratch ? this.scratch.quatB : new this.THREE.Quaternion();
    this.jointState.forEach((state) => {
      const obj = state.object;
      if (!obj) return;

      const isLive = state.hasLiveData && elapsed - state.lastLiveTime <= this.liveDataTimeout;
      let target = state.targetAngle;
      if (!isLive) {
        target = state.neutral;
        state.hasLiveData = false;
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
  }
  setJointAngles(angles = {}) {
    const timestamp = nowSeconds();
    if (!this.modelRoot || this.isDisposed) {
      this.pendingAngles = { ...angles };
      return;
    }
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
    });
  }
  handleResize() {
    if (!this.renderer || !this.camera || !this.container) return;
    const width = this.container.clientWidth || 1;
    const height = this.container.clientHeight || 1;
    this.renderer.setSize(width, height);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
  }
  showFallback(message) {
    if (this.container) {
      this.container.innerHTML = `<div class="robot-virtuel__fallback" data-fallback="true">${message}</div>`;
      this.container.dataset.state = 'error';
    }
  }
  dispose() {
    this.isDisposed = true;
    this.ready = false;
    this.pendingAngles = null;
    if (this.rafId) {
      cancelAnimationFrame(this.rafId);
      this.rafId = null;
    }
    if (this.resizeObserver) {
      this.resizeObserver.disconnect();
      this.resizeObserver = null;
    }
    if (this.controls) {
      this.controls.dispose();
      this.controls = null;
    }
    this.disposeBatteryHUD();
    this.batteryStatus = null;
    if (this.renderer) {
      this.renderer.dispose();
      if (this.renderer.domElement && this.renderer.domElement.parentNode === this.container) {
        this.container.removeChild(this.renderer.domElement);
      }
      this.renderer = null;
    }
    if (this.modelRoot && this.scene) {
      this.scene.remove(this.modelRoot);
    }
    this.modelRoot = null;
    this.pivots = { upperPitch: null, upperRoll: null, knee: null };
    this.baseCompensation = null;
    this.scene = null;
    this.camera = null;
    this.clock = null;
    this.jointState.clear();
    this.scratch = null;
  }
}
