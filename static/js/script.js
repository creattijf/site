// script.js
import * as THREE from 'three';
import Lenis from 'lenis';
import gsap from 'gsap';
import ScrollTrigger from 'gsap/ScrollTrigger';
import SplitType from 'split-type';

gsap.registerPlugin(ScrollTrigger);

document.addEventListener('DOMContentLoaded', () => {
    const lenis = new Lenis();
    function raf(time) {
        lenis.raf(time);
        requestAnimationFrame(raf);
    }
    requestAnimationFrame(raf);

    // --- Генерация client_id и сохранение ---
    function getClientId() {
        let clientId = localStorage.getItem('client_id');
        if (!clientId) {
            clientId = crypto.randomUUID();
            localStorage.setItem('client_id', clientId);
        }
        return clientId;
    }

    function init3DScene() {
        const container = document.getElementById('canvas-container');
        if (!container) return;
        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(75, container.offsetWidth / container.offsetHeight, 0.1, 1000);
        const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
        renderer.setSize(container.offsetWidth, container.offsetHeight);
        renderer.setPixelRatio(window.devicePixelRatio);
        container.appendChild(renderer.domElement);

        const ambientLight = new THREE.AmbientLight(0xffffff, 0.7);
        scene.add(ambientLight);

        const directionalLight = new THREE.DirectionalLight(0xffffff, 1.5);
        directionalLight.position.set(5, 5, 5);
        scene.add(directionalLight);

        camera.position.z = 5;

        const geometry = new THREE.TorusKnotGeometry(1.5, 0.3, 128, 16);
        const material = new THREE.MeshStandardMaterial({ color: 0xC9A864, metalness: 0.8, roughness: 0.3 });
        const knot = new THREE.Mesh(geometry, material);
        scene.add(knot);

        function animate() {
            requestAnimationFrame(animate);
            knot.rotation.x += 0.001;
            knot.rotation.y += 0.002;
            renderer.render(scene, camera);
        }
        animate();

        window.addEventListener('resize', () => {
            camera.aspect = container.offsetWidth / container.offsetHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(container.offsetWidth, container.offsetHeight);
        });
    }

    function initAnimations() {
        gsap.utils.toArray('.section-title, .service-card, .about-text-wrapper p, .about-image-wrapper, .booking-step, .cancellation-section, .info-block, .footer').forEach(elem => {
            gsap.from(elem, {
                y: 60,
                opacity: 0,
                duration: 1.2,
                ease: 'power3.out',
                scrollTrigger: { trigger: elem, start: "top 90%", toggleActions: "play none none none" }
            });
        });
    }

    function initIntro() {
        const title = new SplitType('.hero-title', { types: 'chars' });
        const subtitle = new SplitType('.hero-subtitle', { types: 'chars' });
        const scrollIndicator = document.querySelector('.scroll-down-indicator');

        const tl = gsap.timeline();
        tl.from(title.chars, { y: '110%', opacity: 0, stagger: 0.05, duration: 1, ease: 'power4.out' })
          .from(subtitle.chars, { y: '110%', opacity: 0, stagger: 0.04, duration: 0.8, ease: 'power3.out' }, "-=0.8")
          .to(scrollIndicator, { opacity: 1, duration: 1 }, "-=0.5");
    }

    function init() {
        const preloader = document.querySelector('.preloader');
        gsap.to(preloader, {
            opacity: 0,
            duration: 1,
            delay: 1,
            ease: 'power3.inOut',
            onComplete: () => {
                preloader.style.display = 'none';
                initIntro();
                initAnimations();
            }
        });
        init3DScene();
    }
    init();

    const serviceButtons = document.querySelectorAll('.service-select-btn');
    const serviceInput = document.getElementById('service-input');
    serviceButtons.forEach(button => {
        button.addEventListener('click', () => {
            serviceButtons.forEach(btn => btn.classList.remove('selected'));
            button.classList.add('selected');
            serviceInput.value = button.dataset.serviceName;
        });
    });

    const timeSlotButtons = document.querySelectorAll('.time-slot-btn');
    const dateTimeInput = document.getElementById('booking-datetime-input');
    timeSlotButtons.forEach(button => {
        button.addEventListener('click', () => {
            if (button.classList.contains('available')) {
                timeSlotButtons.forEach(btn => btn.classList.remove('selected'));
                button.classList.add('selected');
                dateTimeInput.value = button.dataset.datetimeIso;
            }
        });
    });

    async function handleFormSubmit(form, url, messageDiv) {
        const submitButton = form.querySelector('button[type="submit"]');
        const originalButtonText = submitButton.textContent;
        submitButton.disabled = true;
        submitButton.textContent = 'Обработка...';

        const formData = new FormData(form);
        const data = Object.fromEntries(formData.entries());
        data.client_id = getClientId(); // Добавляем client_id из localStorage

        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data),
            });
            const result = await response.json();
            messageDiv.textContent = result.message;
            messageDiv.className = `form-message ${response.ok ? 'success' : 'error'}`;
            if (response.ok) {
                setTimeout(() => window.location.reload(), 2000);
            }
        } catch (error) {
            messageDiv.textContent = 'Произошла сетевая ошибка.';
            messageDiv.className = 'form-message error';
        } finally {
            submitButton.disabled = false;
            submitButton.textContent = originalButtonText;
        }
    }

    const bookingForm = document.getElementById('booking-form');
    const formMessage = document.getElementById('form-message');
    bookingForm?.addEventListener('submit', (event) => {
        event.preventDefault();
        if (!serviceInput.value) {
            formMessage.textContent = 'Пожалуйста, выберите услугу.';
            formMessage.className = 'form-message error';
            return;
        }
        if (!dateTimeInput.value) {
            formMessage.textContent = 'Пожалуйста, выберите дату и время.';
            formMessage.className = 'form-message error';
            return;
        }
        handleFormSubmit(bookingForm, '/book', formMessage);
    });

    const cancelForm = document.getElementById('cancel-form');
    const cancelMessage = document.getElementById('cancel-form-message');
    cancelForm?.addEventListener('submit', (event) => {
        event.preventDefault();
        handleFormSubmit(cancelForm, '/cancel', cancelMessage);
    });
});
