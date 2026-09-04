import { RTC_ICE_SERVERS, WSS_URL } from './client-config.mjs';

export function bootClient() {
  // Prevent duplicate listeners and animation loops if the module is loaded twice.
  if (window.__carminaClientBooted) return;
  window.__carminaClientBooted = true;

  // Gameplay constants are kept here so movement, collision, and spell effects use one scale.
  const WS_URL = WSS_URL;
  const MOVE_SPEED = 8.0;
  const ACCELERATION = 20.0;
  const FRICTION = 10.0;
  const BODY_HEIGHT = 0.5;
  const BODY_RADIUS = 0.5;
  const EYE_HEIGHT = BODY_HEIGHT + 0.3;
  const GRAVITY = 18.0;
  const JUMP_SPEED = 13.0;
  const GROUND_FOLLOW_MAX_DROP = 0.5;
  const GROUND_GRACE_PERIOD = 0.12;
  const PLAYER_RADIUS = 0.35;
  const POSITION_SEND_INTERVAL_MS = 100;
  const POSITION_HEARTBEAT_INTERVAL_MS = 1000;
  const POSITION_CHANGE_THRESHOLD = 0.02;
  const ROTATION_CHANGE_THRESHOLD = 0.01;
  const REMOTE_LERP_FACTOR = 0.18;
  const VOICE_VOLUME_UPDATE_INTERVAL_MS = 100;
  const COOLDOWN_UPDATE_INTERVAL_MS = 50;

  const FIRE_DURATION_S = 5;
  const SPELL_COLORS = { fulmine: 0xa3d5ff, scudo: 0x4fd1c5, fuoco: 0xff6b35 };
  const SPELLS_COOLDOWNS = { fulmine: 18000, scudo: 3000, fuoco: 7000 + FIRE_DURATION_S * 1000 };
  const MAX_HP = 100;
  const LIGHTNING_RANGE = 20;
  const FIRE_DEPTH = 5;
  const FIRE_RADIUS_NEAR = 0.5;
  const FIRE_RADIUS_FAR = 2.5;
  const VOICE_CHAT_RADIUS = 15;

  // Cache HUD elements used by damage and health updates.
  const healthFillEl = document.getElementById('healthbar-fill');
  const healthLabelEl = document.getElementById('healthbar-label');
  const damageVignetteEl = document.getElementById('damage-vignette');
  let vignetteFadeTimeout = null;

  function flashDamageVignette(damageAmount) {
    // Briefly tint the screen; the timeout guarantees the effect fades after rapid hits.
    const intensity = Math.min(1, 0.35 + damageAmount / 100);
    damageVignetteEl.style.transition = 'none';
    damageVignetteEl.style.opacity = intensity;
    requestAnimationFrame(() => {
      damageVignetteEl.style.transition = 'opacity 0.6s ease-out';
      damageVignetteEl.style.opacity = 0;
    });
    clearTimeout(vignetteFadeTimeout);
    vignetteFadeTimeout = setTimeout(() => {
      damageVignetteEl.style.opacity = 0;
    }, 700);
  }

  function updateHealthBar(hp) {
    // Clamp health before converting it to the bar height and color.
    const clamped = Math.max(0, Math.min(MAX_HP, hp));
    const fraction = clamped / MAX_HP;
    healthFillEl.style.height = `${fraction * 100}%`;
    healthLabelEl.textContent = Math.round(clamped);
    const hue = fraction * 120;
    healthFillEl.style.background = `hsl(${hue}, 70%, 45%)`;
  }

  // Create the Three.js scene, camera, lighting, and renderer.
  const canvas = document.getElementById('scene');
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.setSize(innerWidth, innerHeight);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x87ceeb);
  scene.fog = new THREE.Fog(0x87ceeb, 15, 55);

  const camera = new THREE.PerspectiveCamera(70, innerWidth / innerHeight, 0.1, 200);
  camera.position.set(0, EYE_HEIGHT, 5);
  camera.rotation.order = 'YXZ';

  window.addEventListener('resize', () => {
    camera.aspect = innerWidth / innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(innerWidth, innerHeight);
  });

  scene.add(new THREE.HemisphereLight(0xffffff, 0x445533, 1.1));
  const sun = new THREE.DirectionalLight(0xfff4e0, 1.2);
  sun.position.set(10, 20, 8);
  scene.add(sun);

  const textureLoader = new THREE.TextureLoader();
  const grassTexture = textureLoader.load('https://cdn.jsdelivr.net/gh/mrdoob/three.js@r128/examples/textures/terrain/grasslight-big.jpg');
  grassTexture.wrapS = grassTexture.wrapT = THREE.RepeatWrapping;
  grassTexture.repeat.set(5, 5);

  // Terrain is received from the server and sampled locally for smooth movement.
  let terrainData = null;

  function buildTerrain(terrain) {
    // Deform a plane mesh with the server height grid.
    terrainData = terrain;
    const { size, resolution, heights } = terrain;

    const geometry = new THREE.PlaneGeometry(size, size, resolution - 1, resolution - 1);
    geometry.rotateX(-Math.PI / 2);

    const positions = geometry.attributes.position;
    for (let iz = 0; iz < resolution; iz++) {
      for (let ix = 0; ix < resolution; ix++) {
        positions.setY(iz * resolution + ix, heights[iz][ix]);
      }
    }
    positions.needsUpdate = true;
    geometry.computeVertexNormals();

    const material = new THREE.MeshStandardMaterial({ map: grassTexture });
    scene.add(new THREE.Mesh(geometry, material));
  }

  function terrainHeightAt(x, z) {
    // Bilinear interpolation keeps movement height continuous between grid points.
    if (!terrainData) return 0;
    const { size, resolution, heights } = terrainData;
    const half = size / 2;

    let gridX = (x + half) / size * (resolution - 1);
    let gridZ = (z + half) / size * (resolution - 1);
    gridX = Math.max(0, Math.min(resolution - 1.001, gridX));
    gridZ = Math.max(0, Math.min(resolution - 1.001, gridZ));

    const x0 = Math.floor(gridX), z0 = Math.floor(gridZ);
    const x1 = x0 + 1, z1 = z0 + 1;
    const tx = gridX - x0, tz = gridZ - z0;

    const h00 = heights[z0][x0], h10 = heights[z0][x1];
    const h01 = heights[z1][x0], h11 = heights[z1][x1];
    const top = h00 * (1 - tx) + h10 * tx;
    const bottom = h01 * (1 - tx) + h11 * tx;
    return top * (1 - tz) + bottom * tz;
  }

  // Every collidable world object is represented by a compact local collision descriptor.
  const obstacles = [];
  const obstacleGrid = new Map();
  const OBSTACLE_CELL_SIZE = 16;
  const COLLISION_QUERY_RADIUS = 16 + PLAYER_RADIUS;

  function obstacleCellKey(cellX, cellZ) {
    return `${cellX},${cellZ}`;
  }

  function registerObstacle(obstacle) {
    obstacle.broadphaseRadius = obstacle.broadphaseRadius
      ?? (obstacle.type === 'box'
        ? Math.hypot(obstacle.halfWidth, obstacle.halfHeight, obstacle.halfDepth)
        : Math.hypot(obstacle.radius || 0, obstacle.halfHeight || 0));
    obstacles.push(obstacle);

    const minCellX = Math.floor((obstacle.x - obstacle.broadphaseRadius) / OBSTACLE_CELL_SIZE);
    const maxCellX = Math.floor((obstacle.x + obstacle.broadphaseRadius) / OBSTACLE_CELL_SIZE);
    const minCellZ = Math.floor((obstacle.z - obstacle.broadphaseRadius) / OBSTACLE_CELL_SIZE);
    const maxCellZ = Math.floor((obstacle.z + obstacle.broadphaseRadius) / OBSTACLE_CELL_SIZE);
    for (let cellX = minCellX; cellX <= maxCellX; cellX++) {
      for (let cellZ = minCellZ; cellZ <= maxCellZ; cellZ++) {
        const key = obstacleCellKey(cellX, cellZ);
        let cell = obstacleGrid.get(key);
        if (!cell) {
          cell = [];
          obstacleGrid.set(key, cell);
        }
        cell.push(obstacle);
      }
    }
  }

  function nearbyObstacles(x, z) {
    const minCellX = Math.floor((x - COLLISION_QUERY_RADIUS) / OBSTACLE_CELL_SIZE);
    const maxCellX = Math.floor((x + COLLISION_QUERY_RADIUS) / OBSTACLE_CELL_SIZE);
    const minCellZ = Math.floor((z - COLLISION_QUERY_RADIUS) / OBSTACLE_CELL_SIZE);
    const maxCellZ = Math.floor((z + COLLISION_QUERY_RADIUS) / OBSTACLE_CELL_SIZE);
    const nearby = new Set();
    for (let cellX = minCellX; cellX <= maxCellX; cellX++) {
      for (let cellZ = minCellZ; cellZ <= maxCellZ; cellZ++) {
        const cell = obstacleGrid.get(obstacleCellKey(cellX, cellZ));
        if (!cell) continue;
        for (const obstacle of cell) nearby.add(obstacle);
      }
    }
    return nearby;
  }

  function ensureObstacleTransform(o) {
    // Older map objects may not include rotation data, so default them to identity transforms.
    if (!o) return;
    if (!o.quaternion) o.quaternion = new THREE.Quaternion();
    if (!o.invQuaternion) o.invQuaternion = o.quaternion.clone().invert();
    if (o.x === undefined) o.x = 0;
    if (o.y === undefined) o.y = 0;
    if (o.z === undefined) o.z = 0;
  }

  function createTree(x, y, z) {
    // Trees render as foliage and a simple cylindrical trunk collider.
    const trunk_radius_top = 0.1;
    const trunk_radius_bottom = 0.2;
    const trunk_height = 1.4;
    const group = new THREE.Group();
    const trunk = new THREE.Mesh(
      new THREE.CylinderGeometry(trunk_radius_top, trunk_radius_bottom, trunk_height, 8),
      new THREE.MeshStandardMaterial({ color: 0x5a3d2b })
    );
    trunk.position.y = 0.7;
    group.add(trunk);

    const cone_radius = 1.1;
    const cone_height = cone_radius * 2;
    const foliage = new THREE.Mesh(
      new THREE.ConeGeometry(cone_radius, cone_height, 8),
      new THREE.MeshStandardMaterial({ color: 0x2e5c2e })
    );
    foliage.position.y = cone_height;
    group.add(foliage);
    group.position.set(x, y, z);
    scene.add(group);

    const quaternion = new THREE.Quaternion();
    const invQuaternion = quaternion.clone().invert();
    registerObstacle({
      type: 'cylinder',
      x, y, z,
      quaternion, invQuaternion,
      radius: trunk_radius_bottom,
      halfHeight: trunk_height / 2,
      radius_top: trunk_radius_top,
      radius_bottom: trunk_radius_bottom,
      height: trunk_height,
    });
  }

  function createBuilding(x, y, z, width, height, depth, color) {
    // Buildings are axis-aligned boxes whose y argument is their base height.
    const boxCenterY = y + height / 2;
    const mesh = new THREE.Mesh(
      new THREE.BoxGeometry(width, height, depth),
      new THREE.MeshStandardMaterial({ color })
    );
    mesh.position.set(x, boxCenterY, z);
    scene.add(mesh);

    const quaternion = new THREE.Quaternion();
    const invQuaternion = quaternion.clone().invert();
    registerObstacle({
      type: 'box',
      x, y: boxCenterY, z,
      quaternion, invQuaternion,
      halfWidth: width / 2,
      halfHeight: height / 2,
      halfDepth: depth / 2,
      minX: x - width / 2, maxX: x + width / 2,
      minZ: z - depth / 2, maxZ: z + depth / 2,
      topY: y + height,
      baseY: y,
    });
  }

  function createRotatedBox(x, y, z, width, height, depth, rotation, color) {
    // Ramps use the same box collider as buildings; y is the object base height.
    const { quaternion, invQuaternion } = makeRotationQuaternions(rotation);
    const boxCenterY = y + height / 2;

    const mesh = new THREE.Mesh(
      new THREE.BoxGeometry(width, height, depth),
      new THREE.MeshStandardMaterial({ color })
    );
    mesh.position.set(x, boxCenterY, z);
    mesh.quaternion.copy(quaternion);
    scene.add(mesh);

    registerObstacle({
      type: 'box', x, y: boxCenterY, z, quaternion, invQuaternion,
      halfWidth: width / 2, halfHeight: height / 2, halfDepth: depth / 2,
    });
  }

  function createColumn(x, y, z, radius, height, rotation, color) {
    // Columns use a cylinder mesh and a matching collider; y is the object base height.
    const { quaternion, invQuaternion } = makeRotationQuaternions(rotation);
    const centerY = y + height / 2;

    const mesh = new THREE.Mesh(
      new THREE.CylinderGeometry(radius, radius, height, 16),
      new THREE.MeshStandardMaterial({ color })
    );
    mesh.position.set(x, centerY, z);
    mesh.quaternion.copy(quaternion);
    scene.add(mesh);

    registerObstacle({
      type: 'cylinder', x, y: centerY, z, quaternion, invQuaternion,
      radius, halfHeight: height / 2,
    });
  }

  function buildWorldFromServer(worldMap) {
    // The server owns layout; this function only turns its object records into client geometry.
    buildTerrain(worldMap.terrain);
    for (const object of worldMap.objects) {
      if (object.type === 'tree') {
        createTree(object.x, object.y, object.z);
      } else if (object.type === 'building') {
        createBuilding(object.x, object.y, object.z, object.width, object.height, object.depth, object.color);
      } else if (object.type === 'platform') {
        createBuilding(object.x, object.y, object.z, object.width, object.height, object.depth, object.color);
      } else if (object.type === 'column') {
        createColumn(object.x, object.y, object.z, object.radius, object.height, object.rotation, object.color);
      } else if (object.type === 'ramp') {
        createRotatedBox(object.x, object.y, object.z, object.width, object.height, object.depth, object.rotation, object.color);
      }
    }
  }

  function createWizard(color) {
    // Build the visible player model; local movement uses the body sphere dimensions below.
    const group = new THREE.Group();

    const bodyMaterial = new THREE.MeshStandardMaterial({ color, emissive: 0x000000, emissiveIntensity: 0 });
    const body = new THREE.Mesh(new THREE.SphereGeometry(0.5, 16, 16), bodyMaterial);
    body.position.y = BODY_HEIGHT;
    group.add(body);

    const head = new THREE.Group();
    head.position.y = BODY_HEIGHT;

    const hat = new THREE.Mesh(
      new THREE.ConeGeometry(0.35, 0.7, 16),
      new THREE.MeshStandardMaterial({ color: 0x1a1a2e })
    );
    hat.position.y = 0.75;
    head.add(hat);

    const nose = new THREE.Mesh(
      new THREE.SphereGeometry(0.1, 6, 6),
      new THREE.MeshStandardMaterial({ color: 0xf5b0b0 })
    );
    nose.position.z = -0.45;
    nose.position.y = 0.18;
    nose.scale.set(1.5, 1, 1);
    head.add(nose);

    const leftEye = new THREE.Mesh(
      new THREE.SphereGeometry(0.04, 6, 6),
      new THREE.MeshStandardMaterial({ color: 0x000000 })
    );
    leftEye.position.set(0.1, 0.26, -0.4);
    head.add(leftEye);

    const rightEye = new THREE.Mesh(
      new THREE.SphereGeometry(0.03, 6, 6),
      new THREE.MeshStandardMaterial({ color: 0x000000 })
    );
    rightEye.position.set(-0.1, 0.26, -0.4);
    head.add(rightEye);

    group.add(head);
    scene.add(group);
    return { group, bodyMaterial, head };
  }

  const localAnchor = new THREE.Object3D();
  scene.add(localAnchor);

  const remotePlayers = {};
  const peerConnections = {};
  const pendingIceCandidates = {};
  const remoteAudio = {};
  let mySlot = null;
  let myHp = MAX_HP;

  function addRemotePlayer(slot, x, z, groundY, yaw, pitch) {
    // Create a remote player and store its latest network target for interpolation.
    if (remotePlayers[slot]) return;
    const color = 0x4040ff + slot * 0x203040;
    const { group, bodyMaterial, head } = createWizard(color);
    group.position.set(x, groundY, z);
    group.rotation.y = yaw;
    head.rotation.x = pitch;
    remotePlayers[slot] = {
      group, bodyMaterial, head,
      targetX: x, targetZ: z, targetGroundY: groundY, targetYaw: yaw, targetPitch: pitch,
      hp: MAX_HP,
    };
  }

  function removeRemotePlayer(slot) {
    closePeerConnection(slot);
    const player = remotePlayers[slot];
    if (!player) return;
    scene.remove(player.group);
    delete remotePlayers[slot];
  }

  function updateRemotePlayer(slot, x, z, groundY, yaw, pitch) {
    // Network packets update targets; rendering eases toward them each frame.
    const player = remotePlayers[slot];
    if (!player) return;
    player.targetX = x;
    player.targetZ = z;
    player.targetGroundY = groundY;
    player.targetYaw = yaw;
    player.targetPitch = pitch;
  }

  function sendRtcSignal(target, signal) {
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    socket.send(JSON.stringify({ type: 'rtc_signal', target, signal }));
  }

  function closePeerConnection(slot) {
    const connection = peerConnections[slot];
    if (connection) {
      connection.onicecandidate = null;
      connection.ontrack = null;
      connection.onconnectionstatechange = null;
      connection.close();
      delete peerConnections[slot];
    }
    delete pendingIceCandidates[slot];

    const audio = remoteAudio[slot];
    if (audio) {
      audio.srcObject = null;
      audio.remove();
      delete remoteAudio[slot];
    }
  }

  async function createPeerConnection(slot, shouldOffer) {
    if (peerConnections[slot]) return peerConnections[slot];

    const connection = new RTCPeerConnection({ iceServers: RTC_ICE_SERVERS });
    peerConnections[slot] = connection;

    if (micStream) {
      for (const track of micStream.getAudioTracks()) {
        connection.addTrack(track, micStream);
      }
    }

    connection.onicecandidate = (event) => {
      if (event.candidate) sendRtcSignal(slot, {
        type: 'candidate',
        candidate: event.candidate.toJSON(),
      });
    };

    connection.ontrack = (event) => {
      let audio = remoteAudio[slot];
      if (!audio) {
        audio = document.createElement('audio');
        audio.autoplay = true;
        audio.playsInline = true;
        audio.setAttribute('aria-hidden', 'true');
        audio.style.display = 'none';
        document.body.appendChild(audio);
        remoteAudio[slot] = audio;
      }
      audio.srcObject = event.streams[0];
    };

    connection.onconnectionstatechange = () => {
      if (['failed', 'closed'].includes(connection.connectionState)) {
        closePeerConnection(slot);
      }
    };

    if (shouldOffer) {
      const offer = await connection.createOffer();
      await connection.setLocalDescription(offer);
      sendRtcSignal(slot, {
        type: 'offer',
        sdp: connection.localDescription.sdp,
      });
    }

    return connection;
  }

  async function handleRtcSignal(message) {
    const slot = message.from;
    const signal = message.signal;
    if (slot === undefined || !signal) return;

    await microphoneReady;

    if (signal.type === 'offer') {
      const connection = await createPeerConnection(slot, false);
      await connection.setRemoteDescription({ type: 'offer', sdp: signal.sdp });
      for (const candidate of pendingIceCandidates[slot] || []) {
        await connection.addIceCandidate(candidate);
      }
      delete pendingIceCandidates[slot];
      const answer = await connection.createAnswer();
      await connection.setLocalDescription(answer);
      sendRtcSignal(slot, {
        type: 'answer',
        sdp: connection.localDescription.sdp,
      });
    } else if (signal.type === 'answer') {
      const connection = peerConnections[slot];
      if (connection) {
        await connection.setRemoteDescription({ type: 'answer', sdp: signal.sdp });
        for (const candidate of pendingIceCandidates[slot] || []) {
          await connection.addIceCandidate(candidate);
        }
        delete pendingIceCandidates[slot];
      }
    } else if (signal.type === 'candidate') {
      const connection = await createPeerConnection(slot, false);
      if (connection.remoteDescription) {
        await connection.addIceCandidate(signal.candidate);
      } else {
        if (!pendingIceCandidates[slot]) pendingIceCandidates[slot] = [];
        pendingIceCandidates[slot].push(signal.candidate);
      }
    }
  }

  function updateVoiceVolumes() {
    for (const slot in remoteAudio) {
      const player = remotePlayers[slot];
      if (!player) {
        remoteAudio[slot].volume = 0;
        continue;
      }
      const distance = Math.hypot(
        camera.position.x - player.group.position.x,
        camera.position.z - player.group.position.z
      );
      const proximity = Math.max(0, 1 - distance / VOICE_CHAT_RADIUS);
      remoteAudio[slot].volume = proximity * proximity;
    }
  }

  let lastVoiceVolumeUpdateAt = 0;

  function updateVoiceVolumesIfDue(now) {
    if (now - lastVoiceVolumeUpdateAt < VOICE_VOLUME_UPDATE_INTERVAL_MS) return;
    lastVoiceVolumeUpdateAt = now;
    updateVoiceVolumes();
  }

  function eyeHeightToGroundOffset(y) {
    return y - EYE_HEIGHT;
  }

  function shortestAngleDelta(from, to) {
    let delta = (to - from) % (Math.PI * 2);
    if (delta > Math.PI) delta -= Math.PI * 2;
    if (delta < -Math.PI) delta += Math.PI * 2;
    return delta;
  }

  let activeParticles = [];
  let activeFires = [];
  const worldPosition = new THREE.Vector3();

  function spawnParticles(color, count, origin) {
    // Create short-lived particles and their per-particle velocities.
    const geometry = new THREE.BufferGeometry();
    const positions = new Float32Array(count * 3);
    const velocities = [];
    for (let i = 0; i < count; i++) {
      positions[i * 3 + 0] = origin.x;
      positions[i * 3 + 1] = origin.y;
      positions[i * 3 + 2] = origin.z;
      velocities.push(new THREE.Vector3((Math.random() - 0.5) * 2, Math.random() * 2 + 0.5, (Math.random() - 0.5) * 2));
    }
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    const material = new THREE.PointsMaterial({ color, size: 0.06, transparent: true, opacity: 1 });
    const points = new THREE.Points(geometry, material);
    scene.add(points);
    activeParticles.push({ points, velocities, born: performance.now(), lifetime: 900 });
  }

  function getBodyMaterial(anchor) {
    return anchor === localAnchor ? null : anchor.userData.bodyMaterial;
  }

  function forwardVector(yaw, pitch) {
    return new THREE.Vector3(
      -Math.cos(pitch) * Math.sin(yaw),
      Math.sin(pitch),
      -Math.cos(pitch) * Math.cos(yaw)
    );
  }

  function getCasterOrientation(slot) {
    if (slot === mySlot) return { yaw: camera.rotation.y, pitch: camera.rotation.x };
    const player = remotePlayers[slot];
    return player ? { yaw: player.group.rotation.y, pitch: player.head.rotation.x } : { yaw: 0, pitch: 0 };
  }

  function getCasterOrigin(slot) {
    if (slot === mySlot) {
      return camera.position.clone();
    }

    const anchor = getEffectAnchor(slot);
    if (!anchor) return new THREE.Vector3();

    const origin = new THREE.Vector3();
    anchor.getWorldPosition(origin);
    origin.y += EYE_HEIGHT - BODY_HEIGHT;
    return origin;
  }

  function generateJaggedPoints(start, end, segments, jitter) {
    const points = [];
    for (let i = 0; i <= segments; i++) {
      const t = i / segments;
      const point = new THREE.Vector3().lerpVectors(start, end, t);
      if (i > 0 && i < segments) {
        point.x += (Math.random() - 0.5) * jitter;
        point.y += (Math.random() - 0.5) * jitter;
        point.z += (Math.random() - 0.5) * jitter;
      }
      points.push(point);
    }
    return points;
  }

  function createBoltMesh(points, radius, color) {
    const curve = new THREE.CatmullRomCurve3(points);
    const geometry = new THREE.TubeGeometry(curve, points.length * 2, radius, 6, false);
    const material = new THREE.MeshBasicMaterial({
      color, transparent: true, opacity: 0.9,
      blending: THREE.AdditiveBlending, depthWrite: false,
    });
    return new THREE.Mesh(geometry, material);
  }

  function castLightning(anchor, forward, targetAnchor) {
    // Render a jagged bolt between the caster and target or a point in front of the caster.
    anchor.getWorldPosition(worldPosition);
    const material = getBodyMaterial(anchor);
    if (material) {
      material.emissive.set(SPELL_COLORS.fulmine);
      material.emissiveIntensity = 2.2;
    }

    const endPoint = new THREE.Vector3();
    if (targetAnchor) {
      targetAnchor.getWorldPosition(endPoint);
    } else {
      endPoint.copy(worldPosition).addScaledVector(forward, LIGHTNING_RANGE);
    }

    const totalLength = worldPosition.distanceTo(endPoint);
    const mainPoints = generateJaggedPoints(worldPosition, endPoint, 12, 0.3);

    const boltMeshes = [];
    const mainMesh = createBoltMesh(mainPoints, 0.05, SPELL_COLORS.fulmine);
    scene.add(mainMesh);
    boltMeshes.push(mainMesh);

    const branchCount = 3 + Math.floor(Math.random() * 3);
    for (let i = 0; i < branchCount; i++) {
      const originIndex = 1 + Math.floor(Math.random() * (mainPoints.length - 2));
      const origin = mainPoints[originIndex];
      const branchLength = totalLength * (0.15 + Math.random() * 0.25);
      const randomDir = new THREE.Vector3(
        (Math.random() - 0.5), (Math.random() - 0.5) * 0.6, (Math.random() - 0.5)
      ).normalize();
      const branchEnd = new THREE.Vector3().copy(origin).addScaledVector(randomDir, branchLength);
      const branchPoints = generateJaggedPoints(origin, branchEnd, 4, branchLength * 0.2);
      const branchMesh = createBoltMesh(branchPoints, 0.02, SPELL_COLORS.fulmine);
      scene.add(branchMesh);
      boltMeshes.push(branchMesh);
    }

    setTimeout(() => {
      boltMeshes.forEach((mesh) => {
        scene.remove(mesh);
        mesh.geometry.dispose();
        mesh.material.dispose();
      });
    }, 150);

    spawnParticles(SPELL_COLORS.fulmine, 20, worldPosition);
    if (targetAnchor) spawnParticles(SPELL_COLORS.fulmine, 20, endPoint);
  }

  function castFire(casterSlot, durationMs) {
    const fireLight = new THREE.PointLight(SPELL_COLORS.fuoco, 2.5, 7);
    scene.add(fireLight);
    activeFires.push({
      casterSlot,
      durationMs,
      startedAt: performance.now(),
      lastSpawnAt: 0,
      fireLight,
    });
  }

  function updateFireEffects(now) {
    activeFires = activeFires.filter((fire) => {
      const elapsed = now - fire.startedAt;
      if (elapsed >= fire.durationMs) {
        scene.remove(fire.fireLight);
        return false;
      }

      const casterOrigin = getCasterOrigin(fire.casterSlot);
      const { yaw, pitch } = getCasterOrientation(fire.casterSlot);
      const fireForward = forwardVector(yaw, pitch);
      const up = Math.abs(fireForward.y) > 0.99
        ? new THREE.Vector3(1, 0, 0)
        : new THREE.Vector3(0, 1, 0);
      const right = new THREE.Vector3().crossVectors(fireForward, up).normalize();
      const trueUp = new THREE.Vector3().crossVectors(right, fireForward).normalize();

      fire.fireLight.position
        .copy(casterOrigin)
        .addScaledVector(fireForward, FIRE_DEPTH * 0.5);

      if (elapsed - fire.lastSpawnAt >= 90) {
        fire.lastSpawnAt = elapsed;
        spawnConeParticles(
          SPELL_COLORS.fuoco,
          14,
          casterOrigin,
          fireForward,
          right,
          trueUp
        );
        fire.fireLight.intensity = 1.8 + Math.random() * 1.4;
      }
      return true;
    });
  }

  function spawnConeParticles(color, count, origin, forward, right, up) {
    // Distribute particles inside an expanding cone aligned with the spell direction.
    const geometry = new THREE.BufferGeometry();
    const positions = new Float32Array(count * 3);
    const velocities = [];
    for (let i = 0; i < count; i++) {
      const depthT = Math.random();
      const depth = depthT * FIRE_DEPTH;
      const radiusHere = FIRE_RADIUS_NEAR + depthT * (FIRE_RADIUS_FAR - FIRE_RADIUS_NEAR);
      const angle = Math.random() * Math.PI * 2;
      const lateral = Math.random() * radiusHere;

      const point = new THREE.Vector3()
        .copy(origin)
        .addScaledVector(forward, depth)
        .addScaledVector(right, Math.cos(angle) * lateral)
        .addScaledVector(up, Math.sin(angle) * lateral);

      positions[i * 3 + 0] = point.x;
      positions[i * 3 + 1] = point.y;
      positions[i * 3 + 2] = point.z;

      velocities.push(
        new THREE.Vector3()
          .addScaledVector(forward, 1.5)
          .add(new THREE.Vector3((Math.random() - 0.5) * 1.5, Math.random() * 1.2, (Math.random() - 0.5) * 1.5))
      );
    }
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    const material = new THREE.PointsMaterial({ color, size: 0.08, transparent: true, opacity: 1 });
    const points = new THREE.Points(geometry, material);
    scene.add(points);
    activeParticles.push({ points, velocities, born: performance.now(), lifetime: 700 });
  }

  function flashDamage(player) {
    player.bodyMaterial.emissive.set(0xff0000);
    player.bodyMaterial.emissiveIntensity = 2.0;
  }

  function castShield(anchor) {
    // Attach a temporary expanding shield mesh to the player's anchor.
    if (anchor.userData.shieldMesh) {
      const previousShield = anchor.userData.shieldMesh;
      anchor.remove(previousShield);
      previousShield.geometry.dispose();
      previousShield.material.dispose();
    }
    const mesh = new THREE.Mesh(
      new THREE.SphereGeometry(0.9, 32, 32),
      new THREE.MeshBasicMaterial({ color: SPELL_COLORS.scudo, transparent: true, opacity: 0.22, side: THREE.DoubleSide })
    );
    mesh.position.y = BODY_HEIGHT;
    mesh.scale.setScalar(0.01);
    mesh.userData.born = performance.now();
    anchor.add(mesh);
    anchor.userData.shieldMesh = mesh;
  }

  function getEffectAnchor(slot) {
    if (slot === mySlot) return localAnchor;
    const player = remotePlayers[slot];
    return player ? player.group : null;
  }

  function attachBodyMaterial(slot) {
    const player = remotePlayers[slot];
    if (player) player.group.userData.bodyMaterial = player.bodyMaterial;
  }

  // Cooldowns are client-side presentation; the server remains authoritative for spell rules.
  const lastLocalCast = { fulmine: 0, scudo: 0, fuoco: 0 };
  const cooldownBars = {};
  document.querySelectorAll('.fill').forEach((el) => {
    cooldownBars[el.dataset.spell] = el;
  });

  function updateCooldownBars() {
    const now = performance.now();
    for (const name in cooldownBars) {
      const fraction = Math.min((now - lastLocalCast[name]) / SPELLS_COOLDOWNS[name], 1);
      cooldownBars[name].style.transform = `scaleX(${fraction})`;
    }
  }

  let lastCooldownUpdateAt = 0;

  function updateCooldownBarsIfDue(now) {
    if (now - lastCooldownUpdateAt < COOLDOWN_UPDATE_INTERVAL_MS) return;
    lastCooldownUpdateAt = now;
    updateCooldownBars();
  }

  // Pointer lock controls connect mouse look and keyboard movement to the camera.
  // Use the actual rendered surface, not document.body, to avoid invalid-document lock errors.
  const pointerLockTarget = canvas || document.body;
  const controls = new THREE.PointerLockControls(camera, pointerLockTarget);
  const overlay = document.getElementById('overlay');
  const crosshair = document.getElementById('crosshair');
  const hud = document.getElementById('hud');

  controls.addEventListener('lock', () => {
    overlay.style.display = 'none';
    crosshair.style.display = 'block';
  });
  controls.addEventListener('unlock', () => {
    overlay.style.display = 'flex';
    crosshair.style.display = 'none';
  });

  // Movement state is separated from velocity so airborne acceleration can be preserved.
  const keys = { forward: false, backward: false, left: false, right: false };
  let velocityX = 0;
  let velocityZ = 0;
  let verticalVelocity = 0;
  let isGrounded = true;
  let groundedGraceTime = GROUND_GRACE_PERIOD;
  let horizontalMovementStartX = 0;
  let horizontalMovementStartZ = 0;

  document.addEventListener('keydown', (e) => {
    if (e.code === 'KeyM' && !e.repeat) {
      setMicrophoneEnabled(!microphoneEnabled);
      return;
    }
    setKey(e.code, true);
    if (e.code === 'Space' && (isGrounded || groundedGraceTime > 0) && controls.isLocked) {
      verticalVelocity = JUMP_SPEED;
      isGrounded = false;
      groundedGraceTime = 0;
    }
  });
  document.addEventListener('keyup', (e) => setKey(e.code, false));

  function setKey(code, value) {
    // Translate browser key codes into the four movement flags.
    if (code === 'KeyW') keys.forward = value;
    if (code === 'KeyS') keys.backward = value;
    if (code === 'KeyA') keys.left = value;
    if (code === 'KeyD') keys.right = value;
  }

  function groundHeightAt(x, z) {
    // Return the highest valid downward surface at a horizontal position.
    let height = terrainHeightAt(x, z);
    for (const o of nearbyObstacles(x, z)) {
      const resolver = SURFACE_HEIGHT_RESOLVERS[o.type];
      if (!resolver) continue;
      const h = resolver(o, x, z);
      if (h !== null && h > height) height = h;
    }
    return height;
  }

  function makeRotationQuaternions(rotation) {
    // Keep world/local conversions consistent with each rendered rotated obstacle.
    const euler = new THREE.Euler(rotation?.x || 0, rotation?.y || 0, rotation?.z || 0, 'XYZ');
    const quaternion = new THREE.Quaternion().setFromEuler(euler);
    const invQuaternion = quaternion.clone().invert();
    return { quaternion, invQuaternion };
  }

  function toLocalPoint(o, worldPoint) {
    ensureObstacleTransform(o);
    return worldPoint.clone().sub(new THREE.Vector3(o.x, o.y, o.z)).applyQuaternion(o.invQuaternion);
  }

  function toWorldPoint(o, localPoint) {
    ensureObstacleTransform(o);
    return localPoint.clone().applyQuaternion(o.quaternion).add(new THREE.Vector3(o.x, o.y, o.z));
  }

  function toLocalDirection(o, worldDirection) {
    ensureObstacleTransform(o);
    return worldDirection.clone().applyQuaternion(o.invQuaternion);
  }

  const RAY_TOP = 200;

  function rayVerticalHeightOnBox(o, x, z, direction, originY) {
    // Ray-box intersection used for both roof support and underside head impacts.
    const rayOriginWorld = new THREE.Vector3(x, originY, z);
    const localOrigin = toLocalPoint(o, rayOriginWorld);
    const worldDirection = new THREE.Vector3(0, direction, 0);
    const localDir = toLocalDirection(o, worldDirection);

    const mins = [-o.halfWidth, -o.halfHeight, -o.halfDepth];
    const maxs = [o.halfWidth, o.halfHeight, o.halfDepth];
    const origin = [localOrigin.x, localOrigin.y, localOrigin.z];
    const dir = [localDir.x, localDir.y, localDir.z];

    let tMin = -Infinity, tMax = Infinity;
    for (let i = 0; i < 3; i++) {
      if (Math.abs(dir[i]) < 1e-8) {
        if (origin[i] < mins[i] || origin[i] > maxs[i]) return null;
        continue;
      }
      let t1 = (mins[i] - origin[i]) / dir[i];
      let t2 = (maxs[i] - origin[i]) / dir[i];
      if (t1 > t2) [t1, t2] = [t2, t1];
      tMin = Math.max(tMin, t1);
      tMax = Math.min(tMax, t2);
      if (tMin > tMax) return null;
    }
    if (tMax < 0) return null;
    const tHit = tMin >= 0 ? tMin : tMax;
    return rayOriginWorld.y + tHit * direction;
  }

  function rayDownHeightOnBox(o, x, z) {
    return rayVerticalHeightOnBox(o, x, z, -1, RAY_TOP);
  }

  function rayUpHeightOnBox(o, x, z) {
    return rayVerticalHeightOnBox(o, x, z, 1, -RAY_TOP);
  }

  function rayDownHeightOnCylinder(o, x, z) {
    return rayVerticalHeightOnCylinder(o, x, z, -1, RAY_TOP);
  }

  function rayVerticalHeightOnCylinder(o, x, z, direction, originY) {
    // Ray-cylinder intersection used for column tops and bottoms.
    const rayOriginWorld = new THREE.Vector3(x, originY, z);
    const O = toLocalPoint(o, rayOriginWorld);
    const D = toLocalDirection(o, new THREE.Vector3(0, direction, 0));
    const r = o.radius, hh = o.halfHeight;
    let bestT = null;

    const a = D.x * D.x + D.z * D.z;
    if (a > 1e-8) {
      const b = 2 * (O.x * D.x + O.z * D.z);
      const c = O.x * O.x + O.z * O.z - r * r;
      const disc = b * b - 4 * a * c;
      if (disc >= 0) {
        const sqrtDisc = Math.sqrt(disc);
        for (const t of [(-b - sqrtDisc) / (2 * a), (-b + sqrtDisc) / (2 * a)]) {
          if (t < 0) continue;
          const y = O.y + t * D.y;
          if (y >= -hh && y <= hh && (bestT === null || t < bestT)) bestT = t;
        }
      }
    }

    if (Math.abs(D.y) > 1e-8) {
      for (const capY of [hh, -hh]) {
        const t = (capY - O.y) / D.y;
        if (t < 0) continue;
        const hx = O.x + t * D.x, hz = O.z + t * D.z;
        if (hx * hx + hz * hz <= r * r && (bestT === null || t < bestT)) bestT = t;
      }
    }

    if (bestT === null) return null;
    return rayOriginWorld.y + bestT * direction;
  }

  function rayUpHeightOnCylinder(o, x, z) {
    return rayVerticalHeightOnCylinder(o, x, z, 1, -RAY_TOP);
  }

  function closestPointOnBoxLocal(o, localPoint) {
    return new THREE.Vector3(
      THREE.MathUtils.clamp(localPoint.x, -o.halfWidth, o.halfWidth),
      THREE.MathUtils.clamp(localPoint.y, -o.halfHeight, o.halfHeight),
      THREE.MathUtils.clamp(localPoint.z, -o.halfDepth, o.halfDepth)
    );
  }

  function closestPointOnCylinderLocal(o, localPoint) {
    const clampedY = THREE.MathUtils.clamp(localPoint.y, -o.halfHeight, o.halfHeight);
    const radial = Math.hypot(localPoint.x, localPoint.z);
    const scale = radial > o.radius ? o.radius / radial : 1;
    return new THREE.Vector3(localPoint.x * scale, clampedY, localPoint.z * scale);
  }

  function cylinderContactLocal(o, localPoint) {
    const radial = Math.hypot(localPoint.x, localPoint.z);
    const insideRadial = radial <= o.radius;
    const insideHeight = Math.abs(localPoint.y) <= o.halfHeight;

    if (insideRadial && insideHeight) {
      const radialDistance = o.radius - radial;
      const topDistance = o.halfHeight - localPoint.y;
      const bottomDistance = o.halfHeight + localPoint.y;
      if (radialDistance <= topDistance && radialDistance <= bottomDistance) {
        const normal = radial > 0.0001
          ? new THREE.Vector3(localPoint.x / radial, 0, localPoint.z / radial)
          : new THREE.Vector3(1, 0, 0);
        return {
          point: new THREE.Vector3(normal.x * o.radius, localPoint.y, normal.z * o.radius),
          normal,
          penetration: radialDistance,
        };
      }

      const top = topDistance <= bottomDistance;
      return {
        point: new THREE.Vector3(localPoint.x, top ? o.halfHeight : -o.halfHeight, localPoint.z),
        normal: new THREE.Vector3(0, top ? 1 : -1, 0),
        penetration: top ? topDistance : bottomDistance,
      };
    }

    const point = closestPointOnCylinderLocal(o, localPoint);
    const offset = localPoint.clone().sub(point);
    const distance = offset.length();
    const normal = distance > 0.0001
      ? offset.multiplyScalar(1 / distance)
      : new THREE.Vector3(1, 0, 0);
    return { point, normal, penetration: 0 };
  }

  function applySpherePush(worldPoint, closestWorld, forceEscape = false) {
    // Push the body horizontally out of a nearby curved or corner surface.
    const offset = worldPoint.clone().sub(closestWorld);
    const distance = offset.length();
    if ((!forceEscape && distance >= PLAYER_RADIUS) || distance <= 0.0001) return;

    // A mostly upward contact is support for the body, not a side collision.
    if (offset.y / distance > 0.7) return;

    const horizontal = new THREE.Vector2(offset.x, offset.z);
    const horizontalDistance = horizontal.length();
    if (horizontalDistance <= 0.0001) return;

    if (forceEscape) {
      const escapeDirection = new THREE.Vector2(-offset.x, -offset.z).normalize();
      camera.position.x = closestWorld.x + escapeDirection.x * PLAYER_RADIUS;
      camera.position.z = closestWorld.z + escapeDirection.y * PLAYER_RADIUS;
      return;
    }

    const pushDistance = Math.sqrt(Math.max(0, PLAYER_RADIUS * PLAYER_RADIUS - offset.y * offset.y));
    const factor = pushDistance / horizontalDistance;
    camera.position.x = closestWorld.x + horizontal.x * factor;
    camera.position.z = closestWorld.z + horizontal.y * factor;
  }

  function applyBoxHorizontalPush(o, localPoint) {
    // Resolve only side penetration; vertical contacts are handled by movement grounding.
    const verticalDistance = Math.max(0, Math.abs(localPoint.y) - o.halfHeight);
    if (verticalDistance >= BODY_RADIUS) return;

    const penetrationX = o.halfWidth + PLAYER_RADIUS - Math.abs(localPoint.x);
    const penetrationZ = o.halfDepth + PLAYER_RADIUS - Math.abs(localPoint.z);
    if (penetrationX <= 0 || penetrationZ <= 0) return;

    const pushLocal = localPoint.clone();
    if (penetrationX < penetrationZ) {
      pushLocal.x = Math.sign(localPoint.x || 1) * (o.halfWidth + PLAYER_RADIUS);
    } else {
      pushLocal.z = Math.sign(localPoint.z || 1) * (o.halfDepth + PLAYER_RADIUS);
    }
    const pushWorld = toWorldPoint(o, pushLocal);
    camera.position.x = pushWorld.x;
    camera.position.z = pushWorld.z;
  }

  function resolveBoxCollision(o, feetHeight) {
    // Use the actual rotated box surface so steep ramps and side contacts push correctly.
    const bodyCenter = camera.position.clone();
    bodyCenter.y -= EYE_HEIGHT - BODY_HEIGHT;
    const localPoint = toLocalPoint(o, bodyCenter);
    const closestLocal = closestPointOnBoxLocal(o, localPoint);
    const inside = closestLocal.distanceToSquared(localPoint) <= 0.000001;
    if (inside) {
      const distances = [
        { axis: 'x', value: o.halfWidth - localPoint.x, direction: 1 },
        { axis: 'x', value: o.halfWidth + localPoint.x, direction: -1 },
        { axis: 'z', value: o.halfDepth - localPoint.z, direction: 1 },
        { axis: 'z', value: o.halfDepth + localPoint.z, direction: -1 },
        { axis: 'y', value: o.halfHeight - localPoint.y, direction: 1 },
        { axis: 'y', value: o.halfHeight + localPoint.y, direction: -1 },
      ];
      const exit = distances.reduce((nearest, candidate) => candidate.value < nearest.value ? candidate : nearest);
      closestLocal[exit.axis] = exit.direction * (exit.axis === 'x'
        ? o.halfWidth : exit.axis === 'z' ? o.halfDepth : o.halfHeight);
    }
    const closestWorld = toWorldPoint(o, closestLocal);
    applySpherePush(bodyCenter, closestWorld, inside);
  }

  function resolveCylinderCollision(o, feetHeight) {
    // Use the rotated cylinder contact normal to preserve uphill support.
    const bodyCenter = camera.position.clone();
    bodyCenter.y -= EYE_HEIGHT - BODY_HEIGHT;
    const localPoint = toLocalPoint(o, bodyCenter);
    const contact = cylinderContactLocal(o, localPoint);
    const closestWorld = toWorldPoint(o, contact.point);
    const worldNormal = contact.normal.clone().applyQuaternion(o.quaternion).normalize();
    const offset = bodyCenter.clone().sub(closestWorld);
    const signedDistance = offset.dot(worldNormal);
    const distance = offset.length();
    const touching = contact.penetration > 0 || distance < PLAYER_RADIUS;
    if (!touching) return;

    if (worldNormal.y > 0.35 && verticalVelocity <= 0 && signedDistance >= -0.05) return;
    if (worldNormal.y > 0.35 && signedDistance >= 0 && signedDistance <= PLAYER_RADIUS + 0.05) return;

    const pushDistance = contact.penetration + PLAYER_RADIUS - Math.max(0, signedDistance);
    if (pushDistance <= 0) return;
    camera.position.x += worldNormal.x * pushDistance;
    camera.position.z += worldNormal.z * pushDistance;
  }

  function resolveCircleCollision(o) {
    const dx = camera.position.x - o.x;
    const dz = camera.position.z - o.z;
    const distance = Math.hypot(dx, dz);
    const minDistance = o.radius + PLAYER_RADIUS;
    if (distance < minDistance && distance > 0.0001) {
      const factor = minDistance / distance;
      camera.position.x = o.x + dx * factor;
      camera.position.z = o.z + dz * factor;
    }
  }

  const SURFACE_HEIGHT_RESOLVERS = {
    box: rayDownHeightOnBox,
    cylinder: rayDownHeightOnCylinder,
  };

  const COLLISION_RESOLVERS = {
    circle: resolveCircleCollision,
    box: resolveBoxCollision,
    cylinder: resolveCylinderCollision,
  };

  function resolveHorizontalCollisions(feetHeight) {
    // Multiple passes let intersecting ramps resolve each other instead of depending on map order.
    for (let pass = 0; pass < 3; pass++) {
      let moved = false;
      const beforeX = camera.position.x;
      const beforeZ = camera.position.z;
      for (const o of nearbyObstacles(camera.position.x, camera.position.z)) {
        const resolver = COLLISION_RESOLVERS[o.type];
        if (resolver) resolver(o, feetHeight);
      }
      moved = camera.position.x !== beforeX || camera.position.z !== beforeZ;
      if (!moved) break;
    }
  }

  function moveHorizontallyWithCollisions(deltaX, deltaZ) {
    let startX = camera.position.x;
    let startZ = camera.position.z;
    let remainingX = deltaX;
    let remainingZ = deltaZ;
    const feetHeight = camera.position.y - EYE_HEIGHT;

    for (let iteration = 0; iteration < 3; iteration++) {
      const candidateX = startX + remainingX;
      const candidateZ = startZ + remainingZ;
      camera.position.x = candidateX;
      camera.position.z = candidateZ;
      resolveHorizontalCollisions(feetHeight);

      const correctionX = camera.position.x - candidateX;
      const correctionZ = camera.position.z - candidateZ;
      if (Math.hypot(correctionX, correctionZ) <= 0.00001) return;

      const collisionNormalLength = Math.hypot(correctionX, correctionZ);
      const normalX = correctionX / collisionNormalLength;
      const normalZ = correctionZ / collisionNormalLength;
      let safeT = 0;
      let blockedT = 1;

      // Locate the first colliding point along the requested movement.
      for (let search = 0; search < 8; search++) {
        const midpoint = (safeT + blockedT) / 2;
        const testX = startX + remainingX * midpoint;
        const testZ = startZ + remainingZ * midpoint;
        camera.position.x = testX;
        camera.position.z = testZ;
        resolveHorizontalCollisions(feetHeight);
        const testCorrection = Math.hypot(camera.position.x - testX, camera.position.z - testZ);
        if (testCorrection > 0.00001) blockedT = midpoint;
        else safeT = midpoint;
      }

      startX += remainingX * safeT;
      startZ += remainingZ * safeT;
      const leftoverFactor = 1 - safeT;
      const leftoverX = remainingX * leftoverFactor;
      const leftoverZ = remainingZ * leftoverFactor;
      const normalMovement = leftoverX * normalX + leftoverZ * normalZ;
      remainingX = leftoverX - normalX * normalMovement;
      remainingZ = leftoverZ - normalZ * normalMovement;

      camera.position.x = startX;
      camera.position.z = startZ;
      if (Math.hypot(remainingX, remainingZ) <= 0.00001) return;
    }

    camera.position.x = startX;
    camera.position.z = startZ;
  }

  function updateVerticalMovement(delta) {
    // Apply gravity, stop against ceilings, and land on terrain or descending surfaces.
    if (!controls.isLocked) return;

    const wasGrounded = isGrounded;
    groundedGraceTime = Math.max(0, groundedGraceTime - delta);
    const previousFeetHeight = camera.position.y - EYE_HEIGHT;
    verticalVelocity -= GRAVITY * delta;
    camera.position.y += verticalVelocity * delta;

    const currentFeetHeight = camera.position.y - EYE_HEIGHT;
    for (const o of nearbyObstacles(camera.position.x, camera.position.z)) {
      const resolver = o.type === 'box' ? rayUpHeightOnBox : rayUpHeightOnCylinder;
      if (!resolver) continue;
      const undersideY = resolver(o, camera.position.x, camera.position.z);
      const terrainBodyTop = terrainHeightAt(camera.position.x, camera.position.z)
        + BODY_HEIGHT + BODY_RADIUS;
      if (undersideY !== null && currentFeetHeight < undersideY
        && terrainBodyTop >= undersideY - 0.05) {
        camera.position.x = horizontalMovementStartX;
        camera.position.z = horizontalMovementStartZ;
        break;
      }
    }

    if (verticalVelocity > 0) {
      for (const o of nearbyObstacles(camera.position.x, camera.position.z)) {
        const resolver = o.type === 'box' ? rayUpHeightOnBox : rayUpHeightOnCylinder;
        if (!resolver) continue;
        const undersideY = resolver(o, camera.position.x, camera.position.z);
        const previousBodyTop = previousFeetHeight + BODY_HEIGHT + BODY_RADIUS;
        const currentBodyTop = currentFeetHeight + BODY_HEIGHT + BODY_RADIUS;
        if (undersideY !== null && previousBodyTop <= undersideY + 0.05
          && currentBodyTop >= undersideY) {
          camera.position.y = undersideY + EYE_HEIGHT - BODY_HEIGHT - BODY_RADIUS;
          verticalVelocity = 0;
          break;
        }
      }
    }

    let supportHeight = terrainHeightAt(camera.position.x, camera.position.z);
    if (verticalVelocity <= 0) {
      for (const o of nearbyObstacles(camera.position.x, camera.position.z)) {
        const resolver = SURFACE_HEIGHT_RESOLVERS[o.type];
        if (!resolver) continue;
        const surfaceY = resolver(o, camera.position.x, camera.position.z);
        if (surfaceY === null) continue;
        const landedOnSurface = previousFeetHeight >= surfaceY - 0.05
          && currentFeetHeight <= surfaceY;
        const alreadyOnSurface = currentFeetHeight >= surfaceY - 0.05;
        const risingSupportContact = currentFeetHeight <= surfaceY + BODY_RADIUS
          && previousFeetHeight <= surfaceY + BODY_HEIGHT + BODY_RADIUS;
        if ((landedOnSurface || alreadyOnSurface || risingSupportContact)
          && surfaceY > supportHeight) {
          supportHeight = surfaceY;
        }
      }
    }
    const minCameraY = supportHeight + EYE_HEIGHT;

    if (wasGrounded && verticalVelocity <= 0
      && camera.position.y - minCameraY <= GROUND_FOLLOW_MAX_DROP) {
      camera.position.y = minCameraY;
    }

    if (camera.position.y <= minCameraY) {
      camera.position.y = minCameraY;
      verticalVelocity = 0;
      isGrounded = true;
      groundedGraceTime = GROUND_GRACE_PERIOD;
    } else {
      isGrounded = false;
    }
  }

  let pointerLockRequestPending = false;

  function requestPointerLock() {
    // Delay the browser lock request slightly so it follows the user gesture reliably.
    if (!pointerLockTarget || pointerLockRequestPending) return;
    if (document.pointerLockElement === pointerLockTarget) return;

    pointerLockRequestPending = true;
    setTimeout(() => {
      try {
        if (typeof pointerLockTarget.requestPointerLock === 'function') {
          pointerLockTarget.requestPointerLock();
        } else {
          controls.lock();
        }
      } catch (error) {
        console.warn('Pointer lock unavailable for the current target element:', error);
      } finally {
        pointerLockRequestPending = false;
      }
    }, 40);
  }

  function updateMovement(delta) {
    // Apply grounded/airborne movement and remember the position before this frame's step.
    if (!controls.isLocked) return;

    horizontalMovementStartX = camera.position.x;
    horizontalMovementStartZ = camera.position.z;

    if (isGrounded) {
      let dx = 0, dz = 0;
      if (keys.forward) dz -= 1;
      if (keys.backward) dz += 1;
      if (keys.left) dx -= 1;
      if (keys.right) dx += 1;

      if (dx !== 0 || dz !== 0) {
        const length = Math.hypot(dx, dz);
        dx /= length; dz /= length;

        const moveDirection = new THREE.Vector3(dx, 0, dz).applyQuaternion(camera.quaternion);
        moveDirection.y = 0;
        moveDirection.normalize();

        velocityX = moveDirection.x * MOVE_SPEED;
        velocityZ = moveDirection.z * MOVE_SPEED;

        const step = MOVE_SPEED * delta;
        moveHorizontallyWithCollisions(moveDirection.x * step, moveDirection.z * step);
      } else {
        velocityX = 0;
        velocityZ = 0;
      }
    } else {
      let inputX = 0, inputZ = 0;
      if (keys.forward) inputZ -= 1;
      if (keys.backward) inputZ += 1;
      if (keys.left) inputX -= 1;
      if (keys.right) inputX += 1;

      if (inputX !== 0 || inputZ !== 0) {
        const length = Math.hypot(inputX, inputZ);
        inputX /= length; inputZ /= length;

        const moveDirection = new THREE.Vector3(inputX, 0, inputZ).applyQuaternion(camera.quaternion);
        moveDirection.y = 0;
        moveDirection.normalize();

        velocityX += moveDirection.x * ACCELERATION * delta;
        velocityZ += moveDirection.z * ACCELERATION * delta;
      }

      const speed = Math.hypot(velocityX, velocityZ);
      if (speed > 0) {
        const newSpeed = Math.max(0, speed - FRICTION * delta);
        const scale = newSpeed / speed;
        velocityX *= scale;
        velocityZ *= scale;
      }

      const currentSpeed = Math.hypot(velocityX, velocityZ);
      if (currentSpeed > MOVE_SPEED) {
        const scale = MOVE_SPEED / currentSpeed;
        velocityX *= scale;
        velocityZ *= scale;
      }

      moveHorizontallyWithCollisions(velocityX * delta, velocityZ * delta);
    }
  }

  let socket, audioContext, workletNode, micStream;
  let microphoneReady = Promise.resolve();
  let microphoneEnabled = true;
  let lastPositionSentAt = 0;
  let lastSentPosition = null;

  function setMicrophoneEnabled(enabled) {
    microphoneEnabled = enabled;
    if (micStream) {
      for (const track of micStream.getAudioTracks()) {
        track.enabled = microphoneEnabled;
      }
    }
    if (mySlot !== null) {
      hud.textContent = microphoneEnabled
        ? `Slot ${mySlot + 1} - microfono attivo`
        : `Slot ${mySlot + 1} - microfono disattivato`;
    }
  }

  async function connectToServer() {
    // Open the WebSocket and route world, player, spell, and health messages.
    socket = new WebSocket(WS_URL);
    socket.binaryType = 'arraybuffer';

    socket.onopen = () => {
      lastSentPosition = null;
      lastPositionSentAt = 0;
      hud.textContent = 'Connesso al server...';
    };

    socket.onmessage = async (event) => {
      const message = JSON.parse(event.data);

      if (message.type === 'welcome') {
        mySlot = message.your_slot;
        camera.position.set(message.spawn_x, message.spawn_y, message.spawn_z);
        buildWorldFromServer(message.world_map);
        updateHealthBar(MAX_HP);
        myHp = MAX_HP;
        for (const p of message.players) {
          addRemotePlayer(p.slot, p.x, p.z, eyeHeightToGroundOffset(p.y), p.yaw, p.pitch || 0);
          attachBodyMaterial(p.slot);
          if (p.hp !== undefined) remotePlayers[p.slot].hp = p.hp;
        }
        hud.textContent = `Slot ${mySlot + 1} - richiedo il microfono...`;
        microphoneReady = startMicrophone();
        await microphoneReady;
        for (const p of message.players) {
          if (mySlot < p.slot) await createPeerConnection(p.slot, true);
        }
        hud.textContent = `Slot ${mySlot + 1} - in ascolto`;
        return;
      }

      if (message.type === 'player_connected') {
        addRemotePlayer(message.slot, message.x, message.z, eyeHeightToGroundOffset(message.y), message.yaw, message.pitch || 0);
        attachBodyMaterial(message.slot);
        if (mySlot < message.slot) await createPeerConnection(message.slot, true);
        return;
      }

      if (message.type === 'player_disconnected') {
        removeRemotePlayer(message.slot);
        return;
      }

      if (message.type === 'rtc_signal') {
        await handleRtcSignal(message);
        return;
      }

      if (message.type === 'player_position') {
        updateRemotePlayer(message.slot, message.x, message.z, eyeHeightToGroundOffset(message.y), message.yaw, message.pitch);
        return;
      }

      if (message.type === 'spell') {
        const anchor = getEffectAnchor(message.slot);
        if (message.slot === mySlot) lastLocalCast[message.word] = performance.now();
        if (!anchor) return;

        const { yaw, pitch } = getCasterOrientation(message.slot);
        const forward = forwardVector(yaw, pitch);

        if (message.word === 'fulmine') {
          const targetAnchor = (message.target !== null && message.target !== undefined) ? getEffectAnchor(message.target) : null;
          castLightning(anchor, forward, targetAnchor);
        } else if (message.word === 'fuoco') {
          const material = getBodyMaterial(anchor);
          if (material) {
            material.emissive.set(SPELL_COLORS.fuoco);
            material.emissiveIntensity = 1.6;
          }
          
          castFire(
            message.slot,
            (message.duration || FIRE_DURATION_S) * 1000
          );
        } else if (message.word === 'scudo') {
          castShield(anchor);
        }
      }

      if (message.type === 'health_update') {
        if (message.slot === mySlot) {
          if (message.hp < myHp) {
            flashDamageVignette(myHp - message.hp);
          }
          myHp = message.hp;
          updateHealthBar(message.hp);
        } else if (remotePlayers[message.slot]) {
          remotePlayers[message.slot].hp = message.hp;
          flashDamage(remotePlayers[message.slot]);
        }
        return;
      }

      if (message.type === 'player_down') {
        if (message.slot === mySlot) {
          hud.textContent = 'Sei stato sconfitto... aspetta il respawn';
        } else if (remotePlayers[message.slot]) {
          remotePlayers[message.slot].group.visible = false;
        }
        return;
      }

      if (message.type === 'player_respawn') {
        if (message.slot === mySlot) {
          camera.position.set(message.x, message.y, message.z);
          updateHealthBar(message.hp);
          myHp = message.hp;
          hud.textContent = `Slot ${mySlot + 1} - in ascolto`;
        } else if (remotePlayers[message.slot]) {
          const player = remotePlayers[message.slot];
          const groundY = eyeHeightToGroundOffset(message.y);
          player.group.position.set(message.x, groundY, message.z);
          player.targetX = message.x;
          player.targetZ = message.z;
          player.targetGroundY = groundY;
          player.hp = message.hp;
          player.group.visible = true;
        }
        return;
      }
    };

    socket.onclose = () => {
      for (const slot in peerConnections) closePeerConnection(slot);
      hud.textContent = 'Disconnesso.';
      socket = null;
    };
    socket.onerror = (e) => {
      console.error(e);
      hud.textContent = 'Errore di connessione.';
    };
  }

  async function startMicrophone() {
    // Feed microphone PCM data into the audio worklet and then to the game server.
    micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    setMicrophoneEnabled(microphoneEnabled);
    audioContext = new AudioContext();
    await audioContext.audioWorklet.addModule('./pcm-processor.js');
    const source = audioContext.createMediaStreamSource(micStream);
    workletNode = new AudioWorkletNode(audioContext, 'pcm-processor', {
      processorOptions: { targetSampleRate: 16000, inputSampleRate: audioContext.sampleRate }
    });
    workletNode.port.onmessage = (event) => {
      if (microphoneEnabled && socket && socket.readyState === WebSocket.OPEN) {
        socket.send(event.data);
      }
    };
    source.connect(workletNode);

    for (const slot in peerConnections) {
      for (const track of micStream.getAudioTracks()) {
        peerConnections[slot].addTrack(track, micStream);
      }
    }
  }

  function sendPositionIfDue() {
    // Send changed positions promptly, but keep a low-rate heartbeat while stationary.
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    const now = performance.now();
    if (now - lastPositionSentAt < POSITION_SEND_INTERVAL_MS) return;
    const position = {
      type: 'position',
      x: camera.position.x,
      y: camera.position.y,
      z: camera.position.z,
      yaw: camera.rotation.y,
      pitch: camera.rotation.x,
    };
    const changed = !lastSentPosition
      || Math.abs(position.x - lastSentPosition.x) >= POSITION_CHANGE_THRESHOLD
      || Math.abs(position.y - lastSentPosition.y) >= POSITION_CHANGE_THRESHOLD
      || Math.abs(position.z - lastSentPosition.z) >= POSITION_CHANGE_THRESHOLD
      || Math.abs(shortestAngleDelta(lastSentPosition.yaw, position.yaw)) >= ROTATION_CHANGE_THRESHOLD
      || Math.abs(shortestAngleDelta(lastSentPosition.pitch, position.pitch)) >= ROTATION_CHANGE_THRESHOLD;
    const heartbeatDue = !lastSentPosition
      || now - lastPositionSentAt >= POSITION_HEARTBEAT_INTERVAL_MS;
    if (!changed && !heartbeatDue) return;
    lastPositionSentAt = now;
    lastSentPosition = position;
    socket.send(JSON.stringify(position));
  }

  overlay.addEventListener('click', async () => {
    if (!socket) await connectToServer();
    requestPointerLock();
  });

  let lastFrameTime = performance.now();

  function animate() {
    // Main frame loop: input, physics, networking, effects, and rendering.
    requestAnimationFrame(animate);
    const now = performance.now();
    const delta = Math.min((now - lastFrameTime) / 1000, 0.1);
    lastFrameTime = now;

    updateMovement(delta);
    updateVerticalMovement(delta);
    sendPositionIfDue();

    localAnchor.position.set(
      camera.position.x,
      camera.position.y - (EYE_HEIGHT - BODY_HEIGHT),
      camera.position.z
    );

    for (const slot in remotePlayers) {
      const player = remotePlayers[slot];
      player.group.position.x += (player.targetX - player.group.position.x) * REMOTE_LERP_FACTOR;
      player.group.position.y += (player.targetGroundY - player.group.position.y) * REMOTE_LERP_FACTOR;
      player.group.position.z += (player.targetZ - player.group.position.z) * REMOTE_LERP_FACTOR;
      player.head.rotation.x += shortestAngleDelta(player.head.rotation.x, player.targetPitch) * REMOTE_LERP_FACTOR;
      player.group.rotation.y += shortestAngleDelta(player.group.rotation.y, player.targetYaw) * REMOTE_LERP_FACTOR;

      player.bodyMaterial.emissiveIntensity += (0 - player.bodyMaterial.emissiveIntensity) * 0.04;

      const shield = player.group.userData.shieldMesh;
      if (shield) updateShield(shield);
    }
    updateShield(localAnchor.userData.shieldMesh);
    updateVoiceVolumesIfDue(now);
    updateFireEffects(now);

    activeParticles = activeParticles.filter((p) => {
      const age = now - p.born;
      if (age > p.lifetime) {
        scene.remove(p.points);
        p.points.geometry.dispose();
        p.points.material.dispose();
        return false;
      }
      const positions = p.points.geometry.attributes.position;
      for (let i = 0; i < p.velocities.length; i++) {
        positions.array[i * 3 + 0] += p.velocities[i].x * 0.016;
        positions.array[i * 3 + 1] += p.velocities[i].y * 0.016;
        positions.array[i * 3 + 2] += p.velocities[i].z * 0.016;
        p.velocities[i].y -= 0.03;
      }
      positions.needsUpdate = true;
      p.points.material.opacity = 1 - age / p.lifetime;
      return true;
    });

    updateCooldownBarsIfDue(now);
    renderer.render(scene, camera);
  }

  function updateShield(shield) {
    // Animate shield growth/fade and remove it after its lifetime.
    if (!shield) return;
    const age = performance.now() - shield.userData.born;
    shield.scale.setScalar(Math.min(age / 250, 1));
    shield.material.opacity = 0.22 * Math.max(0, 1 - Math.max(0, age - 1800) / 600);
    if (age > 2400) {
      const parent = shield.parent;
      parent.remove(shield);
      shield.geometry.dispose();
      shield.material.dispose();
      parent.userData.shieldMesh = null;
    }
  }

  animate();
}

export default bootClient;
